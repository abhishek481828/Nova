"""Health Alert Rule Evaluator for Nova v2.0."""

import time
import logging
from typing import Dict, Any, List
from nova.companion.events.event_bus import EventBus
from nova.companion.protocol.schemas import EventMessage

logger = logging.getLogger("nova.companion.health_alerts")


class HealthAlertEvaluator:
    """Evaluates real-time companion device telemetry and publishes health alerts to EventBus."""

    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus

    async def evaluate_telemetry(self, device_id: str, telemetry: Dict[str, Any]) -> List[EventMessage]:
        alerts = []

        # 1. Low Battery Alert (< 15%)
        battery_pct = telemetry.get("battery_percent", 100)
        is_charging = telemetry.get("is_charging", False)
        if battery_pct < 15 and not is_charging:
            evt = EventMessage(
                source=device_id,
                event="health.alert.low_battery",
                payload={"battery_percent": battery_pct, "message": f"Battery low ({battery_pct}%)"}
            )
            alerts.append(evt)
            await self.event_bus.publish(evt)
            logger.warning(f"Health Alert Triggered [{device_id}]: Low Battery ({battery_pct}%)")

        # 2. High Temperature Alert (> 45°C)
        temp_c = telemetry.get("battery_temp", 30.0)
        if temp_c > 45.0:
            evt = EventMessage(
                source=device_id,
                event="health.alert.high_temperature",
                payload={"temperature_c": temp_c, "message": f"Device overheating ({temp_c}°C)"}
            )
            alerts.append(evt)
            await self.event_bus.publish(evt)
            logger.warning(f"Health Alert Triggered [{device_id}]: High Temp ({temp_c}°C)")

        # 3. Storage Almost Full (> 90%)
        storage_pct = telemetry.get("storage_usage_percent", 50.0)
        if storage_pct > 90.0:
            evt = EventMessage(
                source=device_id,
                event="health.alert.storage_full",
                payload={"storage_usage_percent": storage_pct, "message": f"Storage almost full ({storage_pct}%)"}
            )
            alerts.append(evt)
            await self.event_bus.publish(evt)
            logger.warning(f"Health Alert Triggered [{device_id}]: Storage Full ({storage_pct}%)")

        # 4. High RAM Usage (> 90%)
        ram_pct = telemetry.get("ram_usage_percent", 40.0)
        if ram_pct > 90.0:
            evt = EventMessage(
                source=device_id,
                event="health.alert.high_memory",
                payload={"ram_usage_percent": ram_pct, "message": f"Memory usage critical ({ram_pct}%)"}
            )
            alerts.append(evt)
            await self.event_bus.publish(evt)
            logger.warning(f"Health Alert Triggered [{device_id}]: High RAM ({ram_pct}%)")

        return alerts
