"""Device Discovery — Nova Core TCP availability monitor (Python binding)."""

import logging
import socket
import time
from typing import List, Callable, Tuple

logger = logging.getLogger("nova.mobile.hybrid.device_discovery")

PROBE_TIMEOUT = 1.5
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765


class DeviceDiscovery:
    def __init__(self, host: str = DEFAULT_HOST, port: int = DEFAULT_PORT):
        self.host = host
        self.port = port
        self.is_nova_core_online: bool = False
        self.last_latency_ms: int = -1
        self.consecutive_failures: int = 0
        self._listeners: List[Callable[[bool], None]] = []

    def check_now(self) -> bool:
        reachable, latency = self._probe()
        self.is_nova_core_online = reachable
        self.last_latency_ms = latency
        return reachable

    def simulate_online(self, online: bool = True, latency_ms: int = 12):
        """Used in tests and simulation mode to set Core availability."""
        prev = self.is_nova_core_online
        self.is_nova_core_online = online
        self.last_latency_ms = latency_ms if online else -1
        if prev != online:
            for l in self._listeners:
                l(online)

    def add_state_listener(self, listener: Callable[[bool], None]):
        self._listeners.append(listener)

    def _probe(self) -> Tuple[bool, int]:
        try:
            start = time.time()
            with socket.create_connection((self.host, self.port), timeout=PROBE_TIMEOUT):
                elapsed_ms = int((time.time() - start) * 1000)
                self.consecutive_failures = 0
                return True, elapsed_ms
        except Exception:
            self.consecutive_failures += 1
            return False, -1
