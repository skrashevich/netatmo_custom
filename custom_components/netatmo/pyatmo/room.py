"""Module to represent a Netatmo room."""
from .future__ import annotations

import logging
from .taclasses import dataclass
from .ping import TYPE_CHECKING

from .const import _SETROOMTHERMPOINT_REQ, FROSTGUARD, HOME, MANUAL
from .modules.base_class import NetatmoBase
from .modules.device_types import DeviceType

if TYPE_CHECKING:
    from .home import Home
    from .modules.device_types import DeviceCategory
    from .modules.module import Module

LOG = logging.getLogger(__name__)

MODE_MAP = {"schedule": "home"}


@dataclass
class Room(NetatmoBase):
    """Class to represent a Netatmo room."""

    modules: dict[str, Module]
    device_types: set[DeviceType]
    features: set[DeviceCategory]

    climate_type: DeviceType | None = None

    reachable: bool | None = None
    therm_setpoint_temperature: float | None = None
    therm_setpoint_mode: str | None = None
    therm_measured_temperature: float | None = None
    heating_power_request: int | None = None

    def __init__(
        self,
        home: Home,
        room: dict,
        all_modules: dict[str, Module],
    ) -> None:
        super().__init__(room)
        self.home = home
        self.modules = {
            m_id: m
            for m_id, m in all_modules.items()
            if m_id in room.get("module_ids", [])
        }
        self.device_types = set()
        self.features = set()
        self.evaluate_device_type()

    def update_topology(self, raw_data: dict) -> None:
        self.name = raw_data["name"]
        self.modules = {
            m_id: m
            for m_id, m in self.home.modules.items()
            if m_id in raw_data.get("module_ids", [])
        }
        self.evaluate_device_type()

    def evaluate_device_type(self) -> None:
        for module in self.modules.values():
            self.device_types.add(module.device_type)
            if module.device_category is not None:
                self.features.add(module.device_category)

        if "NRV" in self.device_types:
            self.climate_type = DeviceType.NRV
        elif "NATherm1" in self.device_types:
            self.climate_type = DeviceType.NATherm1
        elif "OTM" in self.device_types:
            self.climate_type = DeviceType.OTM

    def update(self, raw_data: dict) -> None:
        self.reachable = raw_data.get("reachable")
        self.therm_measured_temperature = raw_data.get("therm_measured_temperature")
        self.therm_setpoint_mode = raw_data.get("therm_setpoint_mode")
        self.therm_setpoint_temperature = raw_data.get("therm_setpoint_temperature")
        self.heating_power_request = raw_data.get("heating_power_request")

    async def async_therm_manual(
        self,
        temp: float = None,
        end_time: int = None,
    ) -> None:
        await self.async_therm_set(MANUAL, temp, end_time)

    async def async_therm_home(self, end_time: int = None) -> None:
        await self.async_therm_set(HOME, end_time=end_time)

    async def async_therm_frostguard(self, end_time: int = None) -> None:
        await self.async_therm_set(FROSTGUARD, end_time=end_time)

    async def async_therm_set(
        self,
        mode: str,
        temp: float = None,
        end_time: int = None,
    ) -> None:
        """Set room temperature set point."""
        mode = MODE_MAP.get(mode, mode)

        if "OTM" in self.device_types:
            await self._async_therm_set(mode, temp, end_time)

        elif "NRV" in self.device_types or "NATherm1" in self.device_types:
            await self.async_set_thermpoint(mode, temp, end_time)

    async def _async_therm_set(
        self,
        mode: str,
        temp: float = None,
        end_time: int = None,
    ) -> bool:
        json_therm_set: dict[str, list[dict[str, str | int | float]]] = {
            "rooms": [
                {
                    "id": self.entity_id,
                    "therm_setpoint_mode": mode,
                },
            ],
        }

        if temp:
            json_therm_set["rooms"][0]["therm_setpoint_temperature"] = temp

        if end_time:
            json_therm_set["rooms"][0]["therm_setpoint_end_time"] = end_time

        return await self.home.async_set_state(json_therm_set)

    async def async_set_thermpoint(
        self,
        mode: str,
        temp: float = None,
        end_time: int = None,
    ) -> None:
        """Set room temperature set point (NRV, NATherm1)."""
        post_params = {
            "home_id": self.home.entity_id,
            "room_id": self.entity_id,
            "mode": mode,
        }
        # Temp and endtime should only be send when mode=='manual', but netatmo api can
        # handle that even when mode == 'home' and these settings don't make sense
        if temp is not None:
            post_params["temp"] = str(temp)

        if end_time is not None:
            post_params["endtime"] = str(end_time)

        LOG.debug(
            "Setting room (%s) temperature set point to %s until %s",
            self.entity_id,
            temp,
            end_time,
        )
        await self.home.auth.async_post_request(
            url=_SETROOMTHERMPOINT_REQ,
            params=post_params,
        )