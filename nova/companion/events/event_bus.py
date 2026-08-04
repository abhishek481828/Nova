"""Asynchronous Event Bus for Nova v2.0."""

import asyncio
import logging
from typing import Callable, Dict, List, Coroutine, Any
from nova.companion.protocol.schemas import EventMessage

logger = logging.getLogger("nova.companion.events")

# Handler callback signature: async function accepting EventMessage
EventHandler = Callable[[EventMessage], Coroutine[Any, Any, None]]


class EventBus:
    """Decoupled asyncio pub/sub broker for companion events."""

    def __init__(self):
        self._subscribers: Dict[str, List[EventHandler]] = {}

    def subscribe(self, event_type: str, handler: EventHandler):
        """Subscribes an async handler to a specific event type (or '*' for all events)."""
        if event_type not in self._subscribers:
            self._subscribers[event_type] = []
        if handler not in self._subscribers[event_type]:
            self._subscribers[event_type].append(handler)
            logger.debug(f"Subscribed handler {handler.__name__} to event: {event_type}")

    def unsubscribe(self, event_type: str, handler: EventHandler):
        """Unsubscribes a handler from an event type."""
        if event_type in self._subscribers and handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)

    async def publish(self, event: EventMessage):
        """Publishes an event to all matched subscribers asynchronously."""
        logger.info(f"EventBus publishing: {event.event} from device: {event.source}")
        
        # Specific subscribers
        handlers = list(self._subscribers.get(event.event, []))
        # Catch-all subscribers
        handlers.extend(self._subscribers.get("*", []))

        if not handlers:
            return

        tasks = []
        for handler in handlers:
            try:
                tasks.append(asyncio.create_task(handler(event)))
            except Exception as e:
                logger.error(f"Error creating task for event handler {handler}: {e}")

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
