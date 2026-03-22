"""
Module for charging for Renault/Dacia vehicles.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from enum import Enum

from carconnectivity.charging import Charging
from carconnectivity.charging_connector import ChargingConnector
from carconnectivity.vehicle import ElectricVehicle

if TYPE_CHECKING:
    from typing import Optional, Dict

    from carconnectivity.objects import GenericObject


class RenaultCharging(Charging):  # pylint: disable=too-many-instance-attributes
    """
    RenaultCharging class for handling Renault/Dacia vehicle charging information.

    This class extends the Charging class and includes an enumeration of various
    charging states specific to Renault/Dacia vehicles.
    """
    def __init__(self, vehicle: Optional[ElectricVehicle] = None, origin: Optional[Charging] = None, initialization: Optional[Dict] = None) -> None:
        if origin is not None:
            super().__init__(vehicle=vehicle, origin=origin, initialization=initialization)
            self.settings = RenaultCharging.Settings(parent=self, origin=origin.settings)
        else:
            super().__init__(vehicle=vehicle, initialization=initialization)
            self.settings = RenaultCharging.Settings(parent=self, initialization=self.get_initialization('settings'))

    class Settings(Charging.Settings):
        """
        This class represents the settings for Renault car charging.
        """
        def __init__(self, parent: Optional[GenericObject] = None, origin: Optional[Charging.Settings] = None, initialization: Optional[Dict] = None) -> None:
            if origin is not None:
                super().__init__(parent=parent, origin=origin, initialization=initialization)
            else:
                super().__init__(parent=parent, initialization=initialization)

    class RenaultChargingState(Enum):
        """
        Enum representing the various charging states for a Renault/Dacia vehicle.
        """
        WAITING = 'waiting'
        NOT_IN_CHARGE = 'notInCharge'
        WAITING_FOR_PLANNED_CHARGE = 'waitingForPlannedCharge'
        CHARGE_ENDED = 'chargeEnded'
        ENERGY_FLAP_OPENED = 'energyFlapOpened'
        CHARGE_ERROR = 'chargeError'
        IN_CHARGE = 'inCharge'
        UNPLUGGED = 'unplugged'
        DEFAULT = 'defaultValue'
        DISCHARGING = 'discharging'
        UNKNOWN = 'unknown charging state'

    class RenaultChargeMode(Enum):
        """
        Enum class representing different Renault charge modes.
        """
        ALWAYS = 'always'
        SCHEDULE_MODE = 'schedule_mode'
        UNKNOWN = 'unknown charge mode'

    class RenaultPlugState(Enum):
        """
        Enum representing the plug state for a Renault/Dacia vehicle.
        """
        PLUGGED = 'plugged'
        UNPLUGGED = 'unplugged'
        PLUG_ERROR = 'plugError'
        PLUG_UNKNOWN = 'plugUnknown'
        UNKNOWN = 'unknown plug state'


# Mapping of Renault charging states to generic charging states
mapping_renault_charging_state: Dict[RenaultCharging.RenaultChargingState, Charging.ChargingState] = {
    RenaultCharging.RenaultChargingState.WAITING: Charging.ChargingState.READY_FOR_CHARGING,
    RenaultCharging.RenaultChargingState.NOT_IN_CHARGE: Charging.ChargingState.OFF,
    RenaultCharging.RenaultChargingState.WAITING_FOR_PLANNED_CHARGE: Charging.ChargingState.READY_FOR_CHARGING,
    RenaultCharging.RenaultChargingState.CHARGE_ENDED: Charging.ChargingState.READY_FOR_CHARGING,
    RenaultCharging.RenaultChargingState.ENERGY_FLAP_OPENED: Charging.ChargingState.OFF,
    RenaultCharging.RenaultChargingState.CHARGE_ERROR: Charging.ChargingState.ERROR,
    RenaultCharging.RenaultChargingState.IN_CHARGE: Charging.ChargingState.CHARGING,
    RenaultCharging.RenaultChargingState.UNPLUGGED: Charging.ChargingState.OFF,
    RenaultCharging.RenaultChargingState.DEFAULT: Charging.ChargingState.UNKNOWN,
    RenaultCharging.RenaultChargingState.DISCHARGING: Charging.ChargingState.DISCHARGING,
    RenaultCharging.RenaultChargingState.UNKNOWN: Charging.ChargingState.UNKNOWN,
}

# Mapping of Renault plug state to generic plug connection state
mapping_renault_plug_state: Dict[RenaultCharging.RenaultPlugState, ChargingConnector.ChargingConnectorConnectionState] = {
    RenaultCharging.RenaultPlugState.PLUGGED: ChargingConnector.ChargingConnectorConnectionState.CONNECTED,
    RenaultCharging.RenaultPlugState.UNPLUGGED: ChargingConnector.ChargingConnectorConnectionState.DISCONNECTED,
    RenaultCharging.RenaultPlugState.PLUG_ERROR: ChargingConnector.ChargingConnectorConnectionState.INVALID,
    RenaultCharging.RenaultPlugState.PLUG_UNKNOWN: ChargingConnector.ChargingConnectorConnectionState.UNKNOWN,
    RenaultCharging.RenaultPlugState.UNKNOWN: ChargingConnector.ChargingConnectorConnectionState.UNKNOWN,
}
