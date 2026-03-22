"""
Module for climatization for Renault/Dacia vehicles.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from enum import Enum

from carconnectivity.climatization import Climatization
from carconnectivity.vehicle import GenericVehicle

if TYPE_CHECKING:
    from typing import Optional, Dict


class RenaultClimatization(Climatization):  # pylint: disable=too-many-instance-attributes
    """
    RenaultClimatization class for handling Renault/Dacia vehicle climatization information.

    This class extends the Climatization class and includes an enumeration of various
    climatization states specific to Renault/Dacia vehicles.
    """
    def __init__(self, vehicle: Optional[GenericVehicle] = None, origin: Optional[Climatization] = None, initialization: Optional[Dict] = None) -> None:
        if origin is not None:
            super().__init__(origin=origin, initialization=initialization)
            if not isinstance(self.settings, RenaultClimatization.Settings):
                self.settings: Climatization.Settings = RenaultClimatization.Settings(parent=self, origin=origin.settings, initialization=initialization)
        else:
            super().__init__(vehicle=vehicle, initialization=initialization)
            self.settings: Climatization.Settings = RenaultClimatization.Settings(parent=self, initialization=self.get_initialization('settings'))

    class Settings(Climatization.Settings):
        """
        This class represents the settings for a Renault/Dacia car climatization.
        """
        def __init__(self, parent=None, origin: Optional[Climatization.Settings] = None, initialization: Optional[Dict] = None) -> None:
            if origin is not None:
                super().__init__(parent=parent, origin=origin, initialization=initialization)
            else:
                super().__init__(parent=parent, initialization=initialization)

    class RenaultClimatizationState(Enum):
        """
        Enum representing the various HVAC/climatization states for a Renault/Dacia vehicle.
        """
        ON = 'on'
        OFF = 'off'
        PENDING = 'pending'
        ERROR = 'error'
        UNKNOWN = 'unknown climatization state'


# Mapping of Renault HVAC states to generic climatization states
mapping_renault_climatization_state: Dict[RenaultClimatization.RenaultClimatizationState, Climatization.ClimatizationState] = {
    # 'on' indicates active HVAC pre-conditioning; mapped to HEATING as the most common use case
    RenaultClimatization.RenaultClimatizationState.ON: Climatization.ClimatizationState.HEATING,
    RenaultClimatization.RenaultClimatizationState.OFF: Climatization.ClimatizationState.OFF,
    RenaultClimatization.RenaultClimatizationState.PENDING: Climatization.ClimatizationState.VENTILATION,
    RenaultClimatization.RenaultClimatizationState.ERROR: Climatization.ClimatizationState.OFF,
    RenaultClimatization.RenaultClimatizationState.UNKNOWN: Climatization.ClimatizationState.UNKNOWN,
}
