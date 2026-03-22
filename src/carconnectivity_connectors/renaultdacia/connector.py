"""Module implements the connector to interact with the Renault/Dacia API."""
from __future__ import annotations
from typing import TYPE_CHECKING

import threading
import json
import os
import traceback
import logging
import netrc
from datetime import datetime, timezone, timedelta

import requests

from carconnectivity.garage import Garage
from carconnectivity.errors import AuthenticationError, TooManyRequestsError, RetrievalError, \
    TemporaryAuthenticationError
from carconnectivity.util import robust_time_parse, log_extra_keys, config_remove_credentials
from carconnectivity.units import Length, Volume
from carconnectivity.drive import ElectricDrive, CombustionDrive
from carconnectivity.attributes import DurationAttribute, EnumAttribute
from carconnectivity.units import Temperature
from carconnectivity.charging import Charging
from carconnectivity.charging_connector import ChargingConnector
from carconnectivity.enums import ConnectionState
from carconnectivity.climatization import Climatization

from carconnectivity_connectors.base.connector import BaseConnector
from carconnectivity_connectors.renaultdacia.auth.gigya_session import GigyaSession
from carconnectivity_connectors.renaultdacia.vehicle import RenaultVehicle, RenaultElectricVehicle, RenaultCombustionVehicle, \
    RenaultHybridVehicle
from carconnectivity_connectors.renaultdacia.climatization import RenaultClimatization, mapping_renault_climatization_state
from carconnectivity_connectors.renaultdacia.charging import RenaultCharging, mapping_renault_charging_state, mapping_renault_plug_state
from carconnectivity_connectors.renaultdacia._version import __version__

if TYPE_CHECKING:
    from typing import Dict, List, Optional

    from carconnectivity.carconnectivity import CarConnectivity

LOG: logging.Logger = logging.getLogger("carconnectivity.connectors.renaultdacia")
LOG_API: logging.Logger = logging.getLogger("carconnectivity.connectors.renaultdacia-api-debug")

# Locale to API key mapping (Gigya + Kamereon)
GIGYA_URL_EU = "https://accounts.eu1.gigya.com"
GIGYA_URL_US = "https://accounts.us1.gigya.com"
KAMEREON_APIKEY = "YjkKtHmGfaceeuExUDKGxrLZGGvtVS0J"
KAMEREON_URL_EU = "https://api-wired-prod-1-euw1.wrd-aws.com"
KAMEREON_URL_US = "https://api-wired-prod-1-usw2.wrd-aws.com"

AVAILABLE_LOCALES: Dict[str, Dict[str, str]] = {
    "bg_BG": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3__3ER_6lFvXEXHTP_faLtq6eEdbKDXd9F5GoKwzRyZq37ZQ-db7mXcLzR1Jtls5sn",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "cs_CZ": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_oRlKr5PCVL_sPWUZdJ8c5NOl5Ej8nIZw7VKG7S9Rg36UkDszFzfHfxCaUAUU5or2",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "da_DK": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_5x-2C8b1R4MJPQXkwTPdIqgBpcw653Dakw_ZaEneQRkTBdg9UW9Qg_5G-tMNrTMc",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "de_DE": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_7PLksOyBRkHv126x5WhHb-5pqC1qFR8pQjxSeLB6nhAnPERTUlwnYoznHSxwX668",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "de_AT": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3__B4KghyeUb0GlpU62ZXKrjSfb7CPzwBS368wioftJUL5qXE0Z_sSy0rX69klXuHy",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "de_CH": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_UyiWZs_1UXYCUqK_1n7l7l44UiI_9N9hqwtREV0-UYA_5X7tOV-VKvnGxPBww4q2",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "en_GB": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_e8d4g4SE_Fo8ahyHwwP7ohLGZ79HKNN2T8NjQqoNnk6Epj6ilyYwKdHUyCw3wuxz",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "en_IE": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_Xn7tuOnT9raLEXuwSI1_sFFZNEJhSD0lv3gxkwFtGI-RY4AgiePBiJ9EODh8d9yo",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "es_ES": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_DyMiOwEaxLcPdBTu63Gv3hlhvLaLbW3ufvjHLeuU8U5bx3zx19t5rEKq7KMwk9f1",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "es_MX": {"gigya_url": GIGYA_URL_US, "gigya_api_key": "3_BFzR-2wfhMhUs5OCy3R8U8IiQcHS-81vF8bteSe8eFrboMTjEWzbf4pY1aHQ7cW0",
              "kamereon_url": KAMEREON_URL_US, "kamereon_api_key": KAMEREON_APIKEY},
    "fi_FI": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_xSRCLDYhk1SwSeYQLI3DmA8t-etfAfu5un51fws125ANOBZHgh8Lcc4ReWSwaqNY",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "fr_FR": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_4LKbCcMMcvjDm3X89LU4z4mNKYKdl_W0oD9w-Jvih21WqgJKtFZAnb9YdUgWT9_a",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "fr_BE": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_ZK9x38N8pzEvdiG7ojWHeOAAej43APkeJ5Av6VbTkeoOWR4sdkRc-wyF72HzUB8X",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "fr_CH": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_h3LOcrKZ9mTXxMI9clb2R1VGAWPke6jMNqMw4yYLz4N7PGjYyD0hqRgIFAIHusSn",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "fr_LU": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_zt44Wl_wT9mnqn-BHrR19PvXj3wYRPQKLcPbGWawlatFR837KdxSZZStbBTDaqnb",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "hr_HR": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_HcDC5GGZ89NMP1jORLhYNNCcXt7M3thhZ85eGrcQaM2pRwrgrzcIRWEYi_36cFj9",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "hu_HU": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_nGDWrkSGZovhnVFv5hdIxyuuCuJGZfNmlRGp7-5kEn9yb0bfIfJqoDa2opHOd3Mu",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "it_IT": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_js8th3jdmCWV86fKR3SXQWvXGKbHoWFv8NAgRbH7FnIBsi_XvCpN_rtLcI07uNuq",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "it_CH": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_gHkmHaGACxSLKXqD_uDDx415zdTw7w8HXAFyvh0qIP0WxnHPMF2B9K_nREJVSkGq",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "nl_NL": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_ZIOtjqmP0zaHdEnPK7h1xPuBYgtcOyUxbsTY8Gw31Fzy7i7Ltjfm-hhPh23fpHT5",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "nl_BE": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_yachztWczt6i1pIMhLIH9UA6DXK6vXXuCDmcsoA4PYR0g35RvLPDbp49YribFdpC",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "no_NO": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_QrPkEJr69l7rHkdCVls0owC80BB4CGz5xw_b0gBSNdn3pL04wzMBkcwtbeKdl1g9",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "pl_PL": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_2YBjydYRd1shr6bsZdrvA9z7owvSg3W5RHDYDp6AlatXw9hqx7nVoanRn8YGsBN8",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "pt_PT": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3__afxovspi2-Ip1E5kNsAgc4_35lpLAKCF6bq4_xXj2I2bFPjIWxAOAQJlIkreKTD",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "ro_RO": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_WlBp06vVHuHZhiDLIehF8gchqbfegDJADPQ2MtEsrc8dWVuESf2JCITRo5I2CIxs",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "ru_RU": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_N_ecy4iDyoRtX8v5xOxewwZLKXBjRgrEIv85XxI0KJk8AAdYhJIi17LWb086tGXR",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "sk_SK": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_e8d4g4SE_Fo8ahyHwwP7ohLGZ79HKNN2T8NjQqoNnk6Epj6ilyYwKdHUyCw3wuxz",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "sl_SI": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_QKt0ADYxIhgcje4F3fj9oVidHsx3JIIk-GThhdyMMQi8AJR0QoHdA62YArVjbZCt",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
    "sv_SE": {"gigya_url": GIGYA_URL_EU, "gigya_api_key": "3_EN5Hcnwanu9_Dqot1v1Aky1YelT5QqG4TxveO0EgKFWZYu03WkeB9FKuKKIWUXIS",
              "kamereon_url": KAMEREON_URL_EU, "kamereon_api_key": KAMEREON_APIKEY},
}

# Kamereon endpoint URL patterns
KAMEREON_COMMERCE_URL = "{kamereon_root_url}/commerce/v1"
KAMEREON_PERSON_URL = "{kamereon_root_url}/commerce/v1/persons/{person_id}"
KAMEREON_VEHICLES_URL = "{kamereon_root_url}/commerce/v1/accounts/{account_id}/vehicles"
KAMEREON_VEHICLE_DATA_URL = (
    "{kamereon_root_url}/commerce/v1/accounts/{account_id}/kamereon/kca/car-adapter/v{version}/cars/{vin}/{endpoint}"
)
KAMEREON_VEHICLE_ACTION_URL = (
    "{kamereon_root_url}/commerce/v1/accounts/{account_id}/kamereon/kca/car-adapter/v{version}/cars/{vin}/{endpoint}"
)


# pylint: disable=too-many-lines
class Connector(BaseConnector):
    """
    Connector class for Renault/Dacia API connectivity.

    Args:
        car_connectivity (CarConnectivity): An instance of CarConnectivity.
        config (Dict): Configuration dictionary containing connection details.
    """
    def __init__(self, connector_id: str, car_connectivity: CarConnectivity, config: Dict, *args,  # pylint: disable=too-many-branches,too-many-statements
                 initialization: Optional[Dict] = None, **kwargs) -> None:
        BaseConnector.__init__(self, connector_id=connector_id, car_connectivity=car_connectivity, config=config,
                               log=LOG, api_log=LOG_API, *args, initialization=initialization, **kwargs)

        self._background_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

        self.connection_state: EnumAttribute[ConnectionState] = EnumAttribute(
            name="connection_state", parent=self, value_type=ConnectionState,
            value=ConnectionState.DISCONNECTED, tags={'connector_custom'}
        )
        self.interval: DurationAttribute = DurationAttribute(name="interval", parent=self, tags={'connector_custom'})
        self.interval.minimum = timedelta(seconds=300)
        self.interval._is_changeable = True  # pylint: disable=protected-access

        LOG.info("Loading renaultdacia connector with config %s", config_remove_credentials(config))

        # Locale
        self.active_config['locale'] = config.get('locale', 'de_DE')
        if self.active_config['locale'] not in AVAILABLE_LOCALES:
            raise ValueError(f"Unsupported locale '{self.active_config['locale']}'. Supported locales: {list(AVAILABLE_LOCALES.keys())}")

        locale_config = AVAILABLE_LOCALES[self.active_config['locale']]
        country = self.active_config['locale'].split('_')[1]

        # Username / password
        self.active_config['username'] = None
        self.active_config['password'] = None
        if 'username' in config and 'password' in config:
            self.active_config['username'] = config['username']
            self.active_config['password'] = config['password']
        else:
            if 'netrc' in config:
                self.active_config['netrc'] = config['netrc']
            else:
                self.active_config['netrc'] = os.path.join(os.path.expanduser("~"), ".netrc")
            try:
                secrets = netrc.netrc(file=self.active_config['netrc'])
                secret: tuple[str, str, str] | None = secrets.authenticators("renaultdacia")
                if secret is None:
                    raise AuthenticationError(
                        f'Authentication using {self.active_config["netrc"]} failed: renaultdacia not found in netrc'
                    )
                self.active_config['username'], _, self.active_config['password'] = secret
            except netrc.NetrcParseError as err:
                LOG.error('Authentication using %s failed: %s', self.active_config['netrc'], err)
                raise AuthenticationError(
                    f'Authentication using {self.active_config["netrc"]} failed: {err}'
                ) from err
            except TypeError as err:
                if 'username' not in config:
                    raise AuthenticationError(
                        f'"renaultdacia" entry was not found in {self.active_config["netrc"]} netrc-file.'
                        ' Create it or provide username and password in config'
                    ) from err
            except FileNotFoundError as err:
                raise AuthenticationError(
                    f'{self.active_config["netrc"]} netrc-file was not found.'
                    ' Create it or provide username and password in config'
                ) from err

        if self.active_config['username'] is None or self.active_config['password'] is None:
            raise AuthenticationError('Username or password not provided')

        # Interval
        self.active_config['interval'] = 300
        if 'interval' in config:
            self.active_config['interval'] = config['interval']
            if self.active_config['interval'] < 300:
                raise ValueError('Interval must be at least 300 seconds')
        self.active_config['max_age'] = self.active_config['interval'] - 1
        if 'max_age' in config:
            self.active_config['max_age'] = config['max_age']
        if 'max_age_static' in config:
            self.active_config['max_age_static'] = config['max_age_static']
        else:
            self.active_config['max_age_static'] = 86400  # 24 hours
        self.interval._set_value(timedelta(seconds=self.active_config['interval']))  # pylint: disable=protected-access

        # Set up Gigya session
        tokenstore = car_connectivity.get_tokenstore()
        token_key = f"carconnectivity-connector-renaultdacia:{self.active_config['username']}"
        saved_tokens = tokenstore.get(token_key)

        self.session: GigyaSession = GigyaSession(
            username=self.active_config['username'],
            password=self.active_config['password'],
            gigya_root_url=locale_config['gigya_url'],
            gigya_api_key=locale_config['gigya_api_key'],
            kamereon_root_url=locale_config['kamereon_url'],
            kamereon_api_key=locale_config['kamereon_api_key'],
            country=country,
            token_store=saved_tokens,
        )
        self._token_key = token_key

        # Perform initial login
        try:
            self.session.login()
        except (AuthenticationError, TemporaryAuthenticationError) as err:
            raise AuthenticationError(f'There was a problem when authenticating with one or multiple services: {err}') from err

        self._elapsed: List[timedelta] = []

    def startup(self) -> None:
        """Start the background polling thread."""
        self._background_thread = threading.Thread(target=self._background_loop, daemon=False)
        self._background_thread.name = 'carconnectivity.connectors.renaultdacia-background'
        self._background_thread.start()
        self.healthy._set_value(value=True)  # pylint: disable=protected-access

    def _background_loop(self) -> None:
        self._stop_event.clear()
        fetch: bool = True
        self.connection_state._set_value(value=ConnectionState.CONNECTING)  # pylint: disable=protected-access
        while not self._stop_event.is_set():
            interval = self.active_config['interval']
            try:
                try:
                    if fetch:
                        self.fetch_all()
                        fetch = False
                except Exception:  # pylint: disable=broad-except
                    LOG.critical('There was an unexpected exception: %s', traceback.format_exc())
                    self.connection_state._set_value(value=ConnectionState.ERROR)  # pylint: disable=protected-access
                    fetch = True
            finally:
                self._stop_event.wait(interval)
                fetch = True

    def fetch_all(self) -> None:  # pylint: disable=too-many-branches,too-many-statements,too-many-locals
        """Fetch all data from the Renault API."""
        self.connection_state._set_value(value=ConnectionState.CONNECTED)  # pylint: disable=protected-access
        start_time = datetime.now(tz=timezone.utc)

        # Persist tokens after login
        self._persist_tokens()

        try:
            person_id = self.session.get_person_id()
        except (AuthenticationError, TemporaryAuthenticationError) as err:
            self.connection_state._set_value(value=ConnectionState.ERROR)  # pylint: disable=protected-access
            raise RetrievalError(f'Failed to retrieve person ID: {err}') from err

        # Get person/accounts
        try:
            person_url = KAMEREON_PERSON_URL.format(
                kamereon_root_url=self.session.kamereon_root_url,
                person_id=person_id,
            )
            person_data = self.session.kamereon_get(person_url)
            LOG_API.debug("Person data: %s", json.dumps(person_data, indent=2))
        except requests.exceptions.HTTPError as err:
            self._handle_http_error(err)
            return
        except (AuthenticationError, TemporaryAuthenticationError) as err:
            self.connection_state._set_value(value=ConnectionState.ERROR)  # pylint: disable=protected-access
            raise RetrievalError(f'Failed to retrieve person data: {err}') from err

        # Collect account IDs
        account_ids: List[str] = []
        if 'accounts' in person_data:
            for account in person_data['accounts']:
                account_id = account.get('accountId')
                if account_id:
                    account_ids.append(account_id)
        elif 'data' in person_data:
            data = person_data['data']
            if isinstance(data, dict) and 'accountId' in data:
                account_ids.append(data['accountId'])

        if not account_ids:
            LOG.warning("No accounts found for person %s", person_id)
            return

        # Fetch vehicles for each account
        garage: Garage = self.car_connectivity.garage
        for account_id in account_ids:
            try:
                vehicles_url = KAMEREON_VEHICLES_URL.format(
                    kamereon_root_url=self.session.kamereon_root_url,
                    account_id=account_id,
                )
                vehicles_data = self.session.kamereon_get(vehicles_url)
                LOG_API.debug("Vehicles data for account %s: %s", account_id, json.dumps(vehicles_data, indent=2))
            except requests.exceptions.HTTPError as err:
                self._handle_http_error(err)
                continue
            except (AuthenticationError, TemporaryAuthenticationError) as err:
                LOG.error("Failed to fetch vehicles for account %s: %s", account_id, err)
                continue

            vehicle_links = vehicles_data.get('vehicleLinks', [])
            for vehicle_link in vehicle_links:
                vin = vehicle_link.get('vin')
                if not vin:
                    continue
                vehicle_details = vehicle_link.get('vehicleDetails', {})
                self._fetch_vehicle(garage, account_id, vin, vehicle_details)

        elapsed = datetime.now(tz=timezone.utc) - start_time
        self._elapsed.append(elapsed)
        LOG.debug("Fetching all data took %s", elapsed)

    def _persist_tokens(self) -> None:
        """Persist session tokens to the token store."""
        tokenstore = self.car_connectivity.get_tokenstore()
        tokenstore[self._token_key] = self.session.save_to_token_store()

    def _handle_http_error(self, err: requests.exceptions.HTTPError) -> None:
        """Handle HTTP errors from the API."""
        if err.response is not None:
            status_code = err.response.status_code
            if status_code == 429:
                raise TooManyRequestsError('Too many requests to the Renault API') from err
            if status_code in (401, 403):
                self.connection_state._set_value(value=ConnectionState.ERROR)  # pylint: disable=protected-access
                raise AuthenticationError(f'Authentication failed with status {status_code}') from err
        raise RetrievalError(f'HTTP error: {err}') from err

    def _fetch_vehicle(self, garage: Garage, account_id: str, vin: str, vehicle_details: Dict) -> None:  # pylint: disable=too-many-branches,too-many-statements
        """Fetch and populate data for a single vehicle."""
        brand = vehicle_details.get('brand', {}).get('label', 'Renault')
        model = vehicle_details.get('model', {}).get('label', '')
        energy = vehicle_details.get('energy', {}).get('code', '')

        LOG.debug("Processing vehicle VIN=%s brand=%s model=%s energy=%s", vin, brand, model, energy)

        # Determine vehicle type based on energy type
        vehicle: Optional[RenaultVehicle] = None
        existing_vehicle = garage.get_vehicle(vin)

        if energy in ('ELEC', 'ELECTRIC'):
            if existing_vehicle is None or not isinstance(existing_vehicle, RenaultElectricVehicle):
                vehicle = RenaultElectricVehicle(vin=vin, garage=garage, managing_connector=self)
                garage.add_vehicle(vin, vehicle)
            else:
                vehicle = existing_vehicle
        elif energy in ('HEV', 'PHEV', 'HYBRID'):
            if existing_vehicle is None or not isinstance(existing_vehicle, RenaultHybridVehicle):
                vehicle = RenaultHybridVehicle(vin=vin, garage=garage, managing_connector=self)
                garage.add_vehicle(vin, vehicle)
            else:
                vehicle = existing_vehicle
        else:
            if existing_vehicle is None or not isinstance(existing_vehicle, RenaultCombustionVehicle):
                vehicle = RenaultCombustionVehicle(vin=vin, garage=garage, managing_connector=self)
                garage.add_vehicle(vin, vehicle)
            else:
                vehicle = existing_vehicle

        if vehicle is None:
            return

        # Populate basic vehicle info
        vehicle.manufacturer._set_value(value=brand)  # pylint: disable=protected-access
        if model:
            vehicle.model._set_value(value=model)  # pylint: disable=protected-access

        # License plate
        license_plate = vehicle_details.get('registrationPlate') or vehicle_details.get('licencePlate')
        if license_plate and vehicle.license_plate is not None:
            vehicle.license_plate._set_value(value=license_plate)  # pylint: disable=protected-access

        # Fetch vehicle data endpoints
        self._fetch_cockpit(account_id, vin, vehicle)
        if isinstance(vehicle, (RenaultElectricVehicle, RenaultHybridVehicle)):
            self._fetch_battery_status(account_id, vin, vehicle)
            self._fetch_charge_mode(account_id, vin, vehicle)
        self._fetch_hvac_status(account_id, vin, vehicle)
        self._fetch_location(account_id, vin, vehicle)

    def _get_vehicle_data_url(self, account_id: str, vin: str, endpoint: str, version: int = 1) -> str:
        """Build URL for a Kamereon vehicle data endpoint."""
        return KAMEREON_VEHICLE_DATA_URL.format(
            kamereon_root_url=self.session.kamereon_root_url,
            account_id=account_id,
            version=version,
            vin=vin,
            endpoint=endpoint,
        )

    def _fetch_cockpit(self, account_id: str, vin: str, vehicle: RenaultVehicle) -> None:  # pylint: disable=too-many-branches
        """Fetch cockpit data (odometer, fuel level) for a vehicle."""
        url = self._get_vehicle_data_url(account_id, vin, 'cockpit', version=2)
        try:
            data = self.session.kamereon_get(url)
            LOG_API.debug("Cockpit data for %s: %s", vin, json.dumps(data, indent=2))
        except requests.exceptions.HTTPError as err:
            if err.response is not None and err.response.status_code in (404, 501):
                LOG.debug("Cockpit endpoint not available for %s", vin)
                return
            LOG.warning("Failed to fetch cockpit data for %s: %s", vin, err)
            return
        except Exception as err:  # pylint: disable=broad-except
            LOG.warning("Failed to fetch cockpit data for %s: %s", vin, err)
            return

        attributes = data.get('data', {}).get('attributes', {})
        if not attributes:
            log_extra_keys(LOG, 'cockpit', data, {'data'})
            return

        # Odometer
        total_mileage = attributes.get('totalMileage')
        if total_mileage is not None and vehicle.odometer is not None:
            vehicle.odometer._set_value(value=float(total_mileage), unit=Length.KM)  # pylint: disable=protected-access

        # Fuel autonomy for combustion vehicles
        if isinstance(vehicle, RenaultCombustionVehicle):
            fuel_autonomy = attributes.get('fuelAutonomy')
            fuel_quantity = attributes.get('fuelQuantity')
            drive: Optional[CombustionDrive] = None
            if vehicle.drives is not None:
                for d in vehicle.drives.drives.values():
                    if isinstance(d, CombustionDrive):
                        drive = d
                        break
            if drive is None and vehicle.drives is not None:
                drive = CombustionDrive(drive_id='combustion', drives=vehicle.drives)
                vehicle.drives.add_drive(drive)
            if drive is not None:
                if fuel_autonomy is not None and drive.range is not None:
                    drive.range._set_value(value=float(fuel_autonomy), unit=Length.KM)  # pylint: disable=protected-access
                if fuel_quantity is not None and drive.fuel_tank is not None and drive.fuel_tank.available_capacity is not None:
                    drive.fuel_tank.available_capacity._set_value(value=float(fuel_quantity), unit=Volume.L)  # pylint: disable=protected-access

        log_extra_keys(LOG, 'cockpit.attributes', attributes,
                       {'totalMileage', 'fuelAutonomy', 'fuelQuantity', 'totalMileageUnit'})

    def _fetch_battery_status(self, account_id: str, vin: str, vehicle: RenaultElectricVehicle) -> None:
        # pylint: disable=too-many-branches,too-many-statements,too-many-locals
        """Fetch battery status for an electric/hybrid vehicle."""
        url = self._get_vehicle_data_url(account_id, vin, 'battery-status', version=2)
        try:
            data = self.session.kamereon_get(url)
            LOG_API.debug("Battery status for %s: %s", vin, json.dumps(data, indent=2))
        except requests.exceptions.HTTPError as err:
            if err.response is not None and err.response.status_code in (404, 501):
                LOG.debug("Battery status endpoint not available for %s", vin)
                return
            LOG.warning("Failed to fetch battery status for %s: %s", vin, err)
            return
        except Exception as err:  # pylint: disable=broad-except
            LOG.warning("Failed to fetch battery status for %s: %s", vin, err)
            return

        attributes = data.get('data', {}).get('attributes', {})
        if not attributes:
            log_extra_keys(LOG, 'battery-status', data, {'data'})
            return

        # Battery level
        battery_level = attributes.get('batteryLevel')
        battery_autonomy = attributes.get('batteryAutonomy')

        # Get or create electric drive
        drive: Optional[ElectricDrive] = None
        if vehicle.drives is not None:
            for d in vehicle.drives.drives.values():
                if isinstance(d, ElectricDrive):
                    drive = d
                    break
        if drive is None and vehicle.drives is not None:
            drive = ElectricDrive(drive_id='electric', drives=vehicle.drives)
            vehicle.drives.add_drive(drive)

        if drive is not None:
            if battery_level is not None and drive.level is not None:
                drive.level._set_value(value=float(battery_level))  # pylint: disable=protected-access
            if battery_autonomy is not None and drive.range is not None:
                drive.range._set_value(value=float(battery_autonomy), unit=Length.KM)  # pylint: disable=protected-access

        # Charging info
        charging_status_str = attributes.get('chargingStatus')
        plug_status_str = attributes.get('plugStatus')
        charging_remaining_time = attributes.get('chargingRemainingTime')
        remaining_time_to_full_charge = attributes.get('remainingTime')
        charging_instantaneous_power = attributes.get('chargingInstantaneousPower')

        if isinstance(vehicle.charging, RenaultCharging):
            charging: RenaultCharging = vehicle.charging

            # Charging state
            if charging_status_str is not None:
                try:
                    renault_state = RenaultCharging.RenaultChargingState(charging_status_str)
                    generic_state = mapping_renault_charging_state.get(renault_state, Charging.ChargingState.UNKNOWN)
                    if charging.state is not None:
                        charging.state._set_value(value=generic_state)  # pylint: disable=protected-access
                except ValueError:
                    LOG.warning("Unknown charging state for %s: %s", vin, charging_status_str)

            # Plug state
            if plug_status_str is not None:
                try:
                    renault_plug = RenaultCharging.RenaultPlugState(plug_status_str)
                    generic_plug = mapping_renault_plug_state.get(
                        renault_plug, ChargingConnector.ChargingConnectorConnectionState.UNKNOWN
                    )
                    if charging.connector is not None and charging.connector.connection_state is not None:
                        charging.connector.connection_state._set_value(value=generic_plug)  # pylint: disable=protected-access
                except ValueError:
                    LOG.warning("Unknown plug state for %s: %s", vin, plug_status_str)

            # Charging remaining time (as estimated completion date)
            time_val = charging_remaining_time or remaining_time_to_full_charge
            if time_val is not None and charging.estimated_date_reached is not None:
                estimated_completion = datetime.now(tz=timezone.utc) + timedelta(minutes=int(time_val))
                charging.estimated_date_reached._set_value(value=estimated_completion)  # pylint: disable=protected-access

            # Charging power
            if charging_instantaneous_power is not None and charging.power is not None:
                charging.power._set_value(value=charging_instantaneous_power)  # pylint: disable=protected-access

        # Timestamp
        timestamp_str = attributes.get('timestamp')
        if timestamp_str:
            try:
                measured = robust_time_parse(timestamp_str)
                # Update the charging state with the measurement time
                if isinstance(vehicle.charging, RenaultCharging) and vehicle.charging.state is not None:
                    vehicle.charging.state._set_value(value=vehicle.charging.state.value, measured=measured)  # pylint: disable=protected-access
            except ValueError as err:
                LOG.debug("Could not parse timestamp for %s: %s", vin, err)

        log_extra_keys(LOG, 'battery-status.attributes', attributes, {
            'batteryLevel', 'batteryAutonomy', 'batteryAvailableEnergy', 'chargingStatus',
            'plugStatus', 'chargingRemainingTime', 'remainingTime', 'chargingInstantaneousPower',
            'timestamp', 'chargeEnergy', 'chargePower',
        })

    def _fetch_charge_mode(self, account_id: str, vin: str, vehicle: RenaultElectricVehicle) -> None:  # pylint: disable=unused-argument
        """Fetch charge mode for an electric/hybrid vehicle."""
        url = self._get_vehicle_data_url(account_id, vin, 'charge-mode', version=1)
        try:
            data = self.session.kamereon_get(url)
            LOG_API.debug("Charge mode for %s: %s", vin, json.dumps(data, indent=2))
        except requests.exceptions.HTTPError as err:
            if err.response is not None and err.response.status_code in (404, 501):
                LOG.debug("Charge mode endpoint not available for %s", vin)
                return
            LOG.warning("Failed to fetch charge mode for %s: %s", vin, err)
            return
        except Exception as err:  # pylint: disable=broad-except
            LOG.warning("Failed to fetch charge mode for %s: %s", vin, err)
            return

        attributes = data.get('data', {}).get('attributes', {})
        if not attributes:
            return

        charge_mode_str = attributes.get('chargeMode')
        if charge_mode_str:
            LOG.debug("Charge mode for %s: %s", vin, charge_mode_str)

        log_extra_keys(LOG, 'charge-mode.attributes', attributes, {'chargeMode'})

    def _fetch_hvac_status(self, account_id: str, vin: str, vehicle: RenaultVehicle) -> None:
        """Fetch HVAC status for a vehicle."""
        url = self._get_vehicle_data_url(account_id, vin, 'hvac-status', version=1)
        try:
            data = self.session.kamereon_get(url)
            LOG_API.debug("HVAC status for %s: %s", vin, json.dumps(data, indent=2))
        except requests.exceptions.HTTPError as err:
            if err.response is not None and err.response.status_code in (404, 501):
                LOG.debug("HVAC status endpoint not available for %s", vin)
                return
            LOG.warning("Failed to fetch HVAC status for %s: %s", vin, err)
            return
        except Exception as err:  # pylint: disable=broad-except
            LOG.warning("Failed to fetch HVAC status for %s: %s", vin, err)
            return

        attributes = data.get('data', {}).get('attributes', {})
        if not attributes:
            return

        hvac_status_str = attributes.get('hvacStatus')
        external_temp = attributes.get('externalTemperature')

        if hvac_status_str and isinstance(vehicle.climatization, RenaultClimatization):
            try:
                renault_hvac_state = RenaultClimatization.RenaultClimatizationState(hvac_status_str)
                generic_state = mapping_renault_climatization_state.get(
                    renault_hvac_state, Climatization.ClimatizationState.UNKNOWN
                )
                if vehicle.climatization.state is not None:
                    vehicle.climatization.state._set_value(value=generic_state)  # pylint: disable=protected-access
            except ValueError:
                LOG.warning("Unknown HVAC state for %s: %s", vin, hvac_status_str)

        if external_temp is not None and vehicle.outside_temperature is not None:
            vehicle.outside_temperature._set_value(value=float(external_temp), unit=Temperature.C)  # pylint: disable=protected-access

        log_extra_keys(LOG, 'hvac-status.attributes', attributes, {
            'hvacStatus', 'externalTemperature', 'socThreshold', 'nextHvacStartDate',
        })

    def _fetch_location(self, account_id: str, vin: str, vehicle: RenaultVehicle) -> None:
        """Fetch location data for a vehicle."""
        url = self._get_vehicle_data_url(account_id, vin, 'location', version=1)
        try:
            data = self.session.kamereon_get(url)
            LOG_API.debug("Location data for %s: %s", vin, json.dumps(data, indent=2))
        except requests.exceptions.HTTPError as err:
            if err.response is not None and err.response.status_code in (404, 501):
                LOG.debug("Location endpoint not available for %s", vin)
                return
            LOG.warning("Failed to fetch location data for %s: %s", vin, err)
            return
        except Exception as err:  # pylint: disable=broad-except
            LOG.warning("Failed to fetch location data for %s: %s", vin, err)
            return

        attributes = data.get('data', {}).get('attributes', {})
        if not attributes:
            return

        latitude = attributes.get('gpsLatitude')
        longitude = attributes.get('gpsLongitude')
        last_updated_str = attributes.get('lastUpdateTime')

        if latitude is not None and longitude is not None and vehicle.position is not None:
            last_updated_ts = None
            if last_updated_str:
                try:
                    last_updated_ts = robust_time_parse(last_updated_str)
                except ValueError as err:
                    LOG.debug("Could not parse location timestamp for %s: %s", vin, err)
            if vehicle.position.latitude is not None:
                vehicle.position.latitude._set_value(value=float(latitude), measured=last_updated_ts)  # pylint: disable=protected-access
            if vehicle.position.longitude is not None:
                vehicle.position.longitude._set_value(value=float(longitude), measured=last_updated_ts)  # pylint: disable=protected-access

        log_extra_keys(LOG, 'location.attributes', attributes, {
            'gpsLatitude', 'gpsLongitude', 'lastUpdateTime',
        })

    def shutdown(self) -> None:
        """Shut down the connector gracefully."""
        self._stop_event.set()
        if self._background_thread is not None:
            self._background_thread.join(timeout=10)
        self._persist_tokens()

    def get_version(self) -> str:
        """Return the connector version."""
        return __version__

    def get_type(self) -> str:
        """Return the connector type identifier."""
        return "renaultdacia"
