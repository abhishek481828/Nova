"""Execution Planner — Builds execution plan with target, timeout, retry, fallback."""

import uuid
import logging
from typing import Optional
from nova.mobile.hybrid.strategy import ExecutionTarget
from nova.mobile.hybrid.routing_engine import RoutingEngine

logger = logging.getLogger("nova.mobile.hybrid.execution_planner")


class ExecutionPlan:
    def __init__(
        self,
        request_id: str,
        raw_text: str,
        intent_name: str,
        primary_target: ExecutionTarget,
        fallback_target: Optional[ExecutionTarget],
        timeout_ms: int,
        max_retries: int,
        requires_nova_core_but_offline: bool
    ):
        self.request_id = request_id
        self.raw_text = raw_text
        self.intent_name = intent_name
        self.primary_target = primary_target
        self.fallback_target = fallback_target
        self.timeout_ms = timeout_ms
        self.max_retries = max_retries
        self.requires_nova_core_but_offline = requires_nova_core_but_offline


class ExecutionPlanner:
    LOCAL_TIMEOUT_MS = 5000
    CORE_TIMEOUT_MS = 15000
    MAX_RETRIES = 2

    def __init__(self, routing_engine: RoutingEngine):
        self.routing_engine = routing_engine

    def plan(self, intent_name: str, raw_text: str) -> ExecutionPlan:
        request_id = str(uuid.uuid4())
        target = self.routing_engine.decide(intent_name, raw_text)
        core_required_offline = self.routing_engine.requires_nova_core_but_offline(intent_name, raw_text)

        plan = ExecutionPlan(
            request_id=request_id,
            raw_text=raw_text,
            intent_name=intent_name,
            primary_target=target,
            fallback_target=ExecutionTarget.LOCAL_ANDROID if target == ExecutionTarget.NOVA_CORE else None,
            timeout_ms=self.CORE_TIMEOUT_MS if target == ExecutionTarget.NOVA_CORE else self.LOCAL_TIMEOUT_MS,
            max_retries=self.MAX_RETRIES if target == ExecutionTarget.NOVA_CORE else 0,
            requires_nova_core_but_offline=core_required_offline
        )
        logger.info(f"Planned: intent={intent_name}, target={target.value}, core_offline={core_required_offline}")
        return plan
