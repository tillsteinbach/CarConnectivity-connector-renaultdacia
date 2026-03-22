"""Module for vehicle classes for Renault/Dacia vehicles."""
from __future__ import annotations
from typing import TYPE_CHECKING

from carconnectivity.vehicle import GenericVehicle, ElectricVehicle, CombustionVehicle, HybridVehicle

from carconnectivity_connectors.renaultdacia.climatization import RenaultClimatization
from carconnectivity_connectors.renaultdacia.charging import RenaultCharging

if TYPE_CHECKING:
    from typing import Optional, Dict
    from carconnectivity.garage import Garage
    from carconnectivity_connectors.base.connector import BaseConnector


class RenaultVehicle(GenericVehicle):  # pylint: disable=too-many-instance-attributes
    """
    A class to represent a generic Renault/Dacia vehicle.

    Attributes:
    -----------
    vin : StringAttribute
        The vehicle identification number (VIN) of the vehicle.
    license_plate : StringAttribute
        The license plate of the vehicle.
    """
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(self, vin: Optional[str] = None, garage: Optional[Garage] = None,
                 managing_connector: Optional[BaseConnector] = None,
                 origin: Optional[RenaultVehicle] = None,
                 initialization: Optional[Dict] = None) -> None:
        if origin is not None:
            super().__init__(garage=garage, origin=origin, initialization=initialization)
        else:
            super().__init__(vin=vin, garage=garage, managing_connector=managing_connector,
                             initialization=initialization)
            self.climatization = RenaultClimatization(vehicle=self, origin=self.climatization,
                                                      initialization=self.get_initialization('climatization'))


class RenaultElectricVehicle(ElectricVehicle, RenaultVehicle):
    """
    Represents a Renault/Dacia electric vehicle.
    """
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(self, vin: Optional[str] = None, garage: Optional[Garage] = None,
                 managing_connector: Optional[BaseConnector] = None,
                 origin: Optional[RenaultVehicle] = None,
                 initialization: Optional[Dict] = None) -> None:
        if origin is not None:
            super().__init__(garage=garage, origin=origin, initialization=initialization)
            if isinstance(origin, ElectricVehicle):
                self.charging = RenaultCharging(vehicle=self, origin=origin.charging)
            else:
                self.charging = RenaultCharging(vehicle=self, origin=self.charging)
        else:
            super().__init__(vin=vin, garage=garage, managing_connector=managing_connector,
                             initialization=initialization)
            self.charging = RenaultCharging(vehicle=self, initialization=self.get_initialization('charging'))


class RenaultCombustionVehicle(CombustionVehicle, RenaultVehicle):
    """
    Represents a Renault/Dacia combustion vehicle.
    """
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(self, vin: Optional[str] = None, garage: Optional[Garage] = None,
                 managing_connector: Optional[BaseConnector] = None,
                 origin: Optional[RenaultVehicle] = None,
                 initialization: Optional[Dict] = None) -> None:
        if origin is not None:
            super().__init__(garage=garage, origin=origin, initialization=initialization)
        else:
            super().__init__(vin=vin, garage=garage, managing_connector=managing_connector,
                             initialization=initialization)


class RenaultHybridVehicle(HybridVehicle, RenaultElectricVehicle, RenaultCombustionVehicle):  # pylint: disable=too-many-ancestors
    """
    Represents a Renault/Dacia hybrid vehicle.
    """
    # pylint: disable=too-many-arguments,too-many-positional-arguments
    def __init__(self, vin: Optional[str] = None, garage: Optional[Garage] = None,
                 managing_connector: Optional[BaseConnector] = None,
                 origin: Optional[RenaultVehicle] = None,
                 initialization: Optional[Dict] = None) -> None:
        if origin is not None:
            super().__init__(garage=garage, origin=origin, initialization=initialization)
        else:
            super().__init__(vin=vin, garage=garage, managing_connector=managing_connector,
                             initialization=initialization)
