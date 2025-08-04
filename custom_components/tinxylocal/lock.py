"""Lock platform for Tinxy local integration."""

import asyncio
import logging
from typing import Any, cast

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity


from .const import DOMAIN
from .coordinator import TinxyUpdateCoordinator
from .hub import TinxyLocalHub

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up Tinxy locks based on a config entry."""
    coordinator = cast(
        TinxyUpdateCoordinator, hass.data[DOMAIN][entry.entry_id]["coordinator"]
    )
    hubs = hass.data[DOMAIN][entry.entry_id]["hubs"]

    locks = []
    
    device_types = entry.data["device"].get("deviceTypes", [])
    for node in coordinator.nodes:
        device_name = node["name"]

        for index, device in enumerate(node["devices"]):
            if device["type"].lower() == "lock":
                relay_number = index + 1
                entity_name = f"{device_name} {device['name']}"
                device_type = (
                    device_types[index] if index < len(device_types) else "lock"
                )
                lock = TinxyLock(
                    coordinator=coordinator,
                    hub=hubs[0],
                    node_id=node["device_id"],
                    relay_number=relay_number,
                    name=entity_name,
                    device_type=device_type,
                )
                locks.append(lock)

    async_add_entities(locks)


class TinxyLock(CoordinatorEntity, LockEntity):
    """Representation of a Tinxy lock."""

    def __init__(
        self,
        coordinator: TinxyUpdateCoordinator,
        hub: TinxyLocalHub,
        node_id: str,
        relay_number: int,
        name: str,
        device_type: str,
    ) -> None:
        """Initialize the Tinxy lock."""
        super().__init__(coordinator)
        self.coordinator = coordinator
        self.hub = hub
        self.node_id = node_id
        self.relay_number = relay_number
        self._attr_name = name
        self._attr_unique_id = f"{node_id}_{relay_number}"
        self._device_type = device_type
        self._attr_supported_features = LockEntityFeature.OPEN

    @property
    def unique_id(self) -> str:
        """Return a unique ID for the entity."""
        return self._attr_unique_id

    @property
    def available(self) -> bool:
        """Return True if the device status data is available and valid."""
        if self.coordinator.data is None:
            _LOGGER.warning(
                "Coordinator data is not yet available for node %s", self.node_id
            )
            return False
        
        node_data = self.coordinator.data.get(self.node_id, {})
        return bool(node_data) and self.node_id in self.coordinator.device_metadata

    @property
    def device_info(self) -> DeviceInfo | None:
        """Return device information to associate entities with the device."""
        metadata = self.coordinator.device_metadata.get(self.node_id, {})
        device_name = (
            self._attr_name.split(" ")[0] if self._attr_name else "Unknown Device"
        )
        return {
            "identifiers": {(DOMAIN, self.node_id)},
            "name": device_name,
            "manufacturer": "Tinxy",
            "model": metadata.get("model", "Smart Device"),
            "sw_version": metadata.get("firmware", "Unknown"),
        }
    
    @property
    def is_locked(self) -> bool | None:
        """Return true if the lock is locked."""
        if self.coordinator.data is None:
            return False

        node_data = self.coordinator.data.get(self.node_id, {})
        if not node_data:
            return False

        device_data = node_data.get("devices", [])
        if len(device_data) >= self.relay_number:
            status = device_data[self.relay_number - 1].get("status")
            return status == "locked"
        return False
    
    @property
    def is_open(self) -> bool | None:
        """Return true if the lock is open."""
        if self.coordinator.data is None:
            return False

        node_data = self.coordinator.data.get(self.node_id, {})
        if not node_data:
            return False

        device_data = node_data.get("devices", [])
        if len(device_data) >= self.relay_number:
            status = device_data[self.relay_number - 1].get("status")
            return status == "open"
        return False

    @property
    def icon(self) -> str:
        """Return the icon of the lock."""
        return self.hub.get_device_icon(self._device_type)

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the lock."""
        result = await self.hub.tinxy_toggle(
            mqttpass=self.coordinator.nodes[0]["mqtt_password"],
            relay_number=self.relay_number,
            action=1,
            web_session=async_get_clientsession(self.coordinator.hass),
        )
        if result:
            await asyncio.sleep(0.5)
            await self.coordinator.async_request_refresh()

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the lock."""
        result = await self.hub.tinxy_toggle(
            mqttpass=self.coordinator.nodes[0]["mqtt_password"],
            relay_number=self.relay_number,
            action=0,
            web_session=async_get_clientsession(self.coordinator.hass),
        )
        if result:
            await asyncio.sleep(0.5)
            await self.coordinator.async_request_refresh()

