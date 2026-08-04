"""Nova v3.0 — Lifecycle Manager Python Bindings."""

import time
from typing import Dict, Any, List, Callable


class LifecycleEvent:
    def __init__(self, event_name: str, payload: Dict[str, Any] = None):
        self.event_name = event_name
        self.payload = payload or {}
        self.timestamp = time.time()


class LifecycleManager:
    def __init__(self):
        self.listeners: List[Callable[[LifecycleEvent], None]] = []
        self.history: List[LifecycleEvent] = []

    def initialize(self):
        pass

    def subscribe(self, listener: Callable[[LifecycleEvent], None]):
        self.listeners.append(listener)

    def unsubscribe(self, listener: Callable[[LifecycleEvent], None]):
        if listener in self.listeners:
            self.listeners.remove(listener)

    def publish_event(self, event_name: str, payload: Dict[str, Any] = None):
        evt = LifecycleEvent(event_name, payload)
        self.history.append(evt)
        for l in self.listeners:
            l(evt)

    def get_event_history(self) -> List[LifecycleEvent]:
        return list(self.history)
