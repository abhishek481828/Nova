"""Dynamic Capability Discovery Engine for Nova v2.0."""

from typing import Dict, List, Set
from nova.companion.protocol.schemas import CapabilityAdvertisement


class CapabilityDiscoveryEngine:
    def __init__(self):
        # Maps device_id -> Set of capability keys
        self._device_capabilities: Dict[str, Set[str]] = {}

    def register_capabilities(self, advertisement: CapabilityAdvertisement):
        """Registers or updates capabilities advertised by a companion device."""
        caps = set(advertisement.capabilities)
        self._device_capabilities[advertisement.device_id] = caps

    def has_capability(self, device_id: str, capability: str) -> bool:
        """Check if a device supports a specific capability."""
        return capability in self._device_capabilities.get(device_id, set())

    def list_capabilities(self, device_id: str) -> List[str]:
        """Return list of supported capabilities for a device."""
        return sorted(list(self._device_capabilities.get(device_id, set())))

    def find_devices_with_capability(self, capability: str) -> List[str]:
        """Find all online device IDs that advertise a required capability."""
        matching = []
        for device_id, caps in self._device_capabilities.items():
            if capability in caps:
                matching.append(device_id)
        return matching

    def unregister_device(self, device_id: str):
        """Remove capability records when device disconnects."""
        self._device_capabilities.pop(device_id, None)
