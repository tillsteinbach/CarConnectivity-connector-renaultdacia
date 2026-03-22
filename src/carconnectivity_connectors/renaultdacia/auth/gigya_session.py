"""Module implementing Gigya-based authentication for the Renault/Kamereon API."""
from __future__ import annotations
from typing import TYPE_CHECKING

import logging
import time

import requests

from carconnectivity.errors import AuthenticationError, TemporaryAuthenticationError

if TYPE_CHECKING:
    from typing import Optional, Dict, Any

LOG = logging.getLogger("carconnectivity.connectors.renaultdacia.auth")

# Gigya API URL patterns
GIGYA_LOGIN_URL = "{gigya_root_url}/accounts.login"
GIGYA_ACCOUNT_INFO_URL = "{gigya_root_url}/accounts.getAccountInfo"
GIGYA_JWT_URL = "{gigya_root_url}/accounts.getJWT"

# Kamereon person/vehicle URLs
KAMEREON_PERSON_URL = "{kamereon_root_url}/commerce/v1/persons/{person_id}"
KAMEREON_ACCOUNTS_URL = "{kamereon_root_url}/commerce/v1/persons/{person_id}"
KAMEREON_VEHICLES_URL = "{kamereon_root_url}/commerce/v1/accounts/{account_id}/vehicles"
KAMEREON_VEHICLE_DATA_URL = (
    "{kamereon_root_url}/commerce/v1/accounts/{account_id}/kamereon/kca/car-adapter/v{version}/cars/{vin}/{endpoint}"
)

# JWT expiry buffer in seconds (refresh 60 seconds before expiry)
JWT_EXPIRY_BUFFER = 60
# Default JWT lifetime in seconds (15 minutes as set in Gigya request)
JWT_DEFAULT_LIFETIME = 900


class GigyaSession:  # pylint: disable=too-many-instance-attributes
    """
    Handles authentication with the Renault Gigya service and provides
    an authenticated session for the Kamereon API.
    """

    def __init__(  # pylint: disable=too-many-arguments,too-many-positional-arguments
        self,
        username: str,
        password: str,
        gigya_root_url: str,
        gigya_api_key: str,
        kamereon_root_url: str,
        kamereon_api_key: str,
        country: str,
        token_store: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.username: str = username
        self.password: str = password
        self.gigya_root_url: str = gigya_root_url
        self.gigya_api_key: str = gigya_api_key
        self.kamereon_root_url: str = kamereon_root_url
        self.kamereon_api_key: str = kamereon_api_key
        self.country: str = country

        self._login_token: Optional[str] = None
        self._person_id: Optional[str] = None
        self._jwt: Optional[str] = None
        self._jwt_expiry: float = 0.0

        self._session: requests.Session = requests.Session()
        self._session.headers.update({
            "Content-Type": "application/x-www-form-urlencoded",
        })

        # Restore tokens from token store if available
        if token_store:
            self._login_token = token_store.get("login_token")
            self._person_id = token_store.get("person_id")
            self._jwt = token_store.get("jwt")
            self._jwt_expiry = token_store.get("jwt_expiry", 0.0)

    def save_to_token_store(self) -> Dict[str, Any]:
        """Serialize session tokens for persistence."""
        return {
            "login_token": self._login_token,
            "person_id": self._person_id,
            "jwt": self._jwt,
            "jwt_expiry": self._jwt_expiry,
        }

    def login(self) -> None:
        """Authenticate with Gigya using username and password."""
        url = GIGYA_LOGIN_URL.format(gigya_root_url=self.gigya_root_url)
        data = {
            "ApiKey": self.gigya_api_key,
            "loginID": self.username,
            "password": self.password,
        }
        LOG.debug("Logging in to Gigya for user %s", self.username)
        try:
            response = self._session.post(url, data=data, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            raise TemporaryAuthenticationError(f"Gigya login request failed: {err}") from err

        response_data = response.json()
        if response_data.get("errorCode", 0) != 0:
            error_msg = response_data.get("errorMessage", "Unknown error")
            error_code = response_data.get("errorCode", 0)
            LOG.error("Gigya login failed with error %s: %s", error_code, error_msg)
            raise AuthenticationError(f"Gigya login failed ({error_code}): {error_msg}")

        session_info = response_data.get("sessionInfo", {})
        self._login_token = session_info.get("cookieValue") or response_data.get("sessionInfo", {}).get("login_token")
        if not self._login_token:
            raise AuthenticationError("Gigya login did not return a session token")
        LOG.debug("Gigya login successful, token obtained")

    def get_account_info(self) -> None:
        """Retrieve account info from Gigya to get person_id."""
        if not self._login_token:
            self.login()

        url = GIGYA_ACCOUNT_INFO_URL.format(gigya_root_url=self.gigya_root_url)
        data = {
            "ApiKey": self.gigya_api_key,
            "login_token": self._login_token,
        }
        try:
            response = self._session.post(url, data=data, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            raise TemporaryAuthenticationError(f"Gigya getAccountInfo request failed: {err}") from err

        response_data = response.json()
        if response_data.get("errorCode", 0) != 0:
            error_code = response_data.get("errorCode", 0)
            error_msg = response_data.get("errorMessage", "Unknown error")
            LOG.error("Gigya getAccountInfo failed with error %s: %s", error_code, error_msg)
            # Token may be expired - try to re-login
            if error_code in (403005, 403013):
                LOG.info("Gigya token expired, re-logging in")
                self._login_token = None
                self._jwt = None
                self._jwt_expiry = 0.0
                raise TemporaryAuthenticationError(f"Gigya session expired ({error_code}): {error_msg}")
            raise AuthenticationError(f"Gigya getAccountInfo failed ({error_code}): {error_msg}")

        data_section = response_data.get("data", {})
        self._person_id = data_section.get("personId")
        if not self._person_id:
            raise AuthenticationError("Gigya did not return a personId")
        LOG.debug("Gigya account info retrieved, person_id: %s", self._person_id)

    def get_jwt(self) -> str:
        """Get a fresh JWT from Gigya, refreshing if needed."""
        # Check if JWT is still valid
        if self._jwt and time.time() < (self._jwt_expiry - JWT_EXPIRY_BUFFER):
            return self._jwt

        if not self._login_token:
            self.login()

        url = GIGYA_JWT_URL.format(gigya_root_url=self.gigya_root_url)
        data = {
            "ApiKey": self.gigya_api_key,
            "login_token": self._login_token,
            "fields": "data.personId,data.gigyaDataCenter",
            "expiration": JWT_DEFAULT_LIFETIME,
        }
        try:
            response = self._session.post(url, data=data, timeout=30)
            response.raise_for_status()
        except requests.exceptions.RequestException as err:
            raise TemporaryAuthenticationError(f"Gigya getJWT request failed: {err}") from err

        response_data = response.json()
        if response_data.get("errorCode", 0) != 0:
            error_code = response_data.get("errorCode", 0)
            error_msg = response_data.get("errorMessage", "Unknown error")
            LOG.error("Gigya getJWT failed with error %s: %s", error_code, error_msg)
            if error_code in (403005, 403013):
                LOG.info("Gigya token expired, re-logging in")
                self._login_token = None
                self._jwt = None
                self._jwt_expiry = 0.0
                raise TemporaryAuthenticationError(f"Gigya session expired ({error_code}): {error_msg}")
            raise AuthenticationError(f"Gigya getJWT failed ({error_code}): {error_msg}")

        self._jwt = response_data.get("id_token")
        if not self._jwt:
            raise AuthenticationError("Gigya did not return a JWT")
        self._jwt_expiry = time.time() + JWT_DEFAULT_LIFETIME
        LOG.debug("Gigya JWT obtained successfully")
        return self._jwt

    def get_person_id(self) -> str:
        """Get the person ID, fetching from Gigya if not yet known."""
        if not self._person_id:
            self.get_account_info()
        return self._person_id  # type: ignore[return-value]

    def kamereon_get(self, url: str, params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Perform an authenticated GET request to the Kamereon API."""
        jwt = self.get_jwt()
        headers = {
            "Content-type": "application/vnd.api+json",
            "apikey": self.kamereon_api_key,
            "x-gigya-id_token": jwt,
        }
        merged_params: Dict[str, str] = {"country": self.country}
        if params:
            merged_params.update(params)

        LOG.debug("Kamereon GET %s params=%s", url, merged_params)
        try:
            response = self._session.get(url, headers=headers, params=merged_params, timeout=30)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            if err.response is not None and err.response.status_code == 429:
                raise  # Re-raise for caller to handle as TooManyRequestsError
            raise
        except requests.exceptions.RequestException as err:
            raise TemporaryAuthenticationError(f"Kamereon GET request failed: {err}") from err

        return response.json()

    def kamereon_post(self, url: str, json_data: Dict[str, Any], params: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        """Perform an authenticated POST request to the Kamereon API."""
        jwt = self.get_jwt()
        headers = {
            "Content-type": "application/vnd.api+json",
            "apikey": self.kamereon_api_key,
            "x-gigya-id_token": jwt,
        }
        merged_params: Dict[str, str] = {"country": self.country}
        if params:
            merged_params.update(params)

        LOG.debug("Kamereon POST %s params=%s body=%s", url, merged_params, json_data)
        try:
            response = self._session.post(url, headers=headers, params=merged_params, json=json_data, timeout=30)
            response.raise_for_status()
        except requests.exceptions.HTTPError as err:
            if err.response is not None and err.response.status_code == 429:
                raise
            raise
        except requests.exceptions.RequestException as err:
            raise TemporaryAuthenticationError(f"Kamereon POST request failed: {err}") from err

        return response.json()
