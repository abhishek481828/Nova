"""Routing Engine — Combines CapabilityResolver + DeviceDiscovery + RoutingPolicy."""

import logging
from nova.mobile.hybrid.strategy import ExecutionTarget, RoutingPolicy
from nova.mobile.hybrid.capability_resolver import CapabilityResolver
from nova.mobile.hybrid.device_discovery import DeviceDiscovery

logger = logging.getLogger("nova.mobile.hybrid.routing_engine")


class RoutingEngine:
    def __init__(
        self,
        capability_resolver: CapabilityResolver,
        device_discovery: DeviceDiscovery,
        policy: RoutingPolicy = RoutingPolicy.AUTOMATIC
    ):
        self.capability_resolver = capability_resolver
        self.device_discovery = device_discovery
        self.policy = policy

    def decide(self, intent_name: str, raw_text: str) -> ExecutionTarget:
        if self.policy == RoutingPolicy.ALWAYS_LOCAL:
            logger.info("Policy=ALWAYS_LOCAL → LOCAL_ANDROID")
            return ExecutionTarget.LOCAL_ANDROID

        if self.policy == RoutingPolicy.ALWAYS_NOVA_CORE:
            if self.device_discovery.is_nova_core_online:
                return ExecutionTarget.NOVA_CORE
            logger.warning("Policy=ALWAYS_NOVA_CORE but Core offline → fallback LOCAL")
            return ExecutionTarget.LOCAL_ANDROID

        if self.policy == RoutingPolicy.OFFLINE_MODE:
            logger.info("Policy=OFFLINE_MODE → LOCAL_ANDROID enforced")
            return ExecutionTarget.LOCAL_ANDROID

        if self.policy == RoutingPolicy.FALLBACK:
            if self.capability_resolver.is_nova_core_required(raw_text) and self.device_discovery.is_nova_core_online:
                return ExecutionTarget.NOVA_CORE
            return ExecutionTarget.LOCAL_ANDROID

        # AUTOMATIC
        preferred = self.capability_resolver.resolve_target(intent_name, raw_text)
        if preferred == ExecutionTarget.NOVA_CORE and self.device_discovery.is_nova_core_online:
            logger.info("AUTOMATIC → NOVA_CORE (online, capability match)")
            return ExecutionTarget.NOVA_CORE
        if preferred == ExecutionTarget.NOVA_CORE and not self.device_discovery.is_nova_core_online:
            logger.warning("AUTOMATIC → Core required but OFFLINE → degraded LOCAL response")
            return ExecutionTarget.LOCAL_ANDROID
        logger.info("AUTOMATIC → LOCAL_ANDROID")
        return ExecutionTarget.LOCAL_ANDROID

    def requires_nova_core_but_offline(self, intent_name: str, raw_text: str) -> bool:
        preferred = self.capability_resolver.resolve_target(intent_name, raw_text)
        return preferred == ExecutionTarget.NOVA_CORE and not self.device_discovery.is_nova_core_online
