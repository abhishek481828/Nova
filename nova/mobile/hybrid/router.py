"""Hybrid Router — Main orchestrator for Phase 5 (Python binding)."""

import uuid
import time
import logging
from typing import List, Callable, Optional

from nova.mobile.hybrid.strategy import ExecutionTarget, RoutingPolicy
from nova.mobile.hybrid.result import ExecutionResult
from nova.mobile.hybrid.capability_resolver import CapabilityResolver
from nova.mobile.hybrid.device_discovery import DeviceDiscovery
from nova.mobile.hybrid.routing_engine import RoutingEngine
from nova.mobile.hybrid.execution_planner import ExecutionPlanner

logger = logging.getLogger("nova.mobile.hybrid.router")


class HybridRouter:
    """
    Phase 5 Hybrid AI Router.
    Receives recognized speech text, decides the execution target
    (LOCAL_ANDROID or NOVA_CORE), executes accordingly, and returns
    a unified ExecutionResult with a Nova-personality spoken response.
    """

    def __init__(self, command_engine=None, lifecycle_manager=None):
        self.command_engine = command_engine
        self.lifecycle_manager = lifecycle_manager

        self.capability_resolver = CapabilityResolver()
        self.device_discovery = DeviceDiscovery()
        self.routing_engine = RoutingEngine(self.capability_resolver, self.device_discovery)
        self.execution_planner = ExecutionPlanner(self.routing_engine)

        self.result_history: List[ExecutionResult] = []
        self._result_listeners: List[Callable[[ExecutionResult], None]] = []

    def route(self, recognized_text: str, intent_name: str = "UNKNOWN") -> ExecutionResult:
        start_time = time.time()
        plan = self.execution_planner.plan(intent_name, recognized_text)

        self._publish("HybridRouted", {"requestId": plan.request_id, "intent": intent_name, "target": plan.primary_target.value})

        if plan.requires_nova_core_but_offline:
            logger.warning(f"Nova Core required but OFFLINE for '{recognized_text}'")
            self._publish("HybridCoreOffline", {"requestId": plan.request_id})
            result = ExecutionResult(
                request_id=plan.request_id,
                intent=intent_name,
                target=ExecutionTarget.LOCAL_ANDROID,
                is_success=False,
                spoken_response="I can help with phone tasks right now, but this request requires Nova Core, which is currently unavailable.",
                execution_time_ms=int((time.time() - start_time) * 1000),
                error_message="Nova Core offline"
            )
        elif plan.primary_target == ExecutionTarget.NOVA_CORE:
            result = self._forward_to_nova_core(plan, start_time)
        else:
            result = self._execute_locally(plan, start_time)

        self.result_history.append(result)
        self._notify_listeners(result)
        return result

    def _execute_locally(self, plan, start_time: float) -> ExecutionResult:
        try:
            if self.command_engine:
                cmd_result = self.command_engine.execute_text(plan.raw_text)
                self._publish("HybridLocalExecuted", {"requestId": plan.request_id, "response": cmd_result.spoken_response})
                return ExecutionResult(
                    request_id=plan.request_id,
                    intent=plan.intent_name,
                    target=ExecutionTarget.LOCAL_ANDROID,
                    is_success=cmd_result.is_success,
                    spoken_response=cmd_result.spoken_response,
                    execution_time_ms=int((time.time() - start_time) * 1000),
                    error_message=cmd_result.error_message
                )
            else:
                return ExecutionResult(
                    plan.request_id, plan.intent_name, ExecutionTarget.LOCAL_ANDROID, True,
                    spoken_response=f"Executing '{plan.raw_text}' locally.",
                    execution_time_ms=int((time.time() - start_time) * 1000)
                )
        except Exception as e:
            logger.error("Local execution failed", exc_info=True)
            return ExecutionResult(
                plan.request_id, plan.intent_name, ExecutionTarget.LOCAL_ANDROID, False,
                spoken_response="Sorry, I couldn't complete that locally.",
                execution_time_ms=int((time.time() - start_time) * 1000),
                error_message=str(e)
            )

    def _forward_to_nova_core(self, plan, start_time: float) -> ExecutionResult:
        net_start = time.time()
        try:
            self._publish("HybridCoreSent", {"requestId": plan.request_id})
            # WebSocket + JWT forwarding (stub — real WS in Phase 6 / Core integration)
            latency_ms = int((time.time() - net_start) * 1000)
            return ExecutionResult(
                request_id=plan.request_id,
                intent=plan.intent_name,
                target=ExecutionTarget.NOVA_CORE,
                is_success=True,
                spoken_response="Forwarded to Nova Core. Processing your request.",
                execution_time_ms=int((time.time() - start_time) * 1000),
                network_latency_ms=latency_ms
            )
        except Exception as e:
            logger.error("Nova Core forwarding failed — falling back to local", exc_info=True)
            self._publish("HybridFallback", {"requestId": plan.request_id, "reason": str(e)})
            result = self._execute_locally(plan, start_time)
            result.used_fallback = True
            return result

    def add_result_listener(self, listener: Callable[[ExecutionResult], None]):
        self._result_listeners.append(listener)

    def get_last_result(self) -> Optional[ExecutionResult]:
        return self.result_history[-1] if self.result_history else None

    def _notify_listeners(self, result: ExecutionResult):
        for l in self._result_listeners:
            try:
                l(result)
            except Exception:
                logger.error("Error in result listener", exc_info=True)

    def _publish(self, event_name: str, payload: dict):
        if self.lifecycle_manager:
            self.lifecycle_manager.publish_event(event_name, payload)
