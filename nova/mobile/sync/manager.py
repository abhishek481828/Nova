"""SyncManager — Phase 8 Main Orchestrator for Multi-Device Synchronization."""

import time
import logging
from typing import Optional, List, Callable

from nova.mobile.sync.enums import (
    Platform, DeviceStatus, ConflictPolicy, SyncEvent, SyncCategory
)
from nova.mobile.sync.models import (
    DeviceInfo, SyncPayload, SyncConflict, SyncSession, SyncStats
)
from nova.mobile.sync.device_registry import DeviceRegistry
from nova.mobile.sync.conflict_resolver import ConflictResolver
from nova.mobile.sync.repository import SyncRepository
from nova.mobile.sync.sync_engine import SyncEngine

logger = logging.getLogger("nova.mobile.sync.manager")


class SyncManager:
    def __init__(
        self,
        local_device_id: str,
        local_device_name: str,
        local_platform: Platform,
        sync_engine: SyncEngine,
        lifecycle_manager=None,
        conflict_policy: ConflictPolicy = ConflictPolicy.NEWEST_WINS
    ):
        self.local_device_id = local_device_id
        self.local_device_name = local_device_name
        self.local_platform = local_platform
        self._lifecycle_manager = lifecycle_manager

        self.device_registry = DeviceRegistry()
        self.repository = SyncRepository()
        self.conflict_resolver = ConflictResolver(conflict_policy)
        self.sync_engine = sync_engine

        self._total_sent = 0
        self._total_received = 0
        self._last_sync_timestamp = 0.0
        self._result_listeners: List[Callable] = []

    def start(self):
        self.device_registry.register(DeviceInfo(
            device_id=self.local_device_id,
            device_name=self.local_device_name,
            platform=self.local_platform,
            version="3.0.0",
            capabilities={"MEMORY_SYNC", "ROUTINE_SYNC", "SESSION_CONTINUITY"},
            status=DeviceStatus.ONLINE,
            is_authenticated=True
        ))
        self._publish(SyncEvent.SYNC_RESTORED, {"device": self.local_device_name})
        logger.info(f"SyncManager started for '{self.local_device_name}'")

    def stop(self):
        self.device_registry.mark_offline(self.local_device_id)
        self._publish(SyncEvent.DEVICE_LEFT, {"device": self.local_device_name})
        logger.info("SyncManager stopped")

    # ── Device Management ──────────────────────────────────────────────────────

    def register_device(self, device: DeviceInfo) -> bool:
        ok = self.device_registry.register(device)
        if ok:
            self._publish(SyncEvent.DEVICE_JOINED,
                          {"deviceId": device.device_id, "name": device.device_name})
            logger.info(f"Device joined: '{device.device_name}'")
        return ok

    def authenticate_device(self, device_id: str) -> bool:
        ok = self.device_registry.authenticate(device_id)
        if ok:
            self._publish(SyncEvent.DEVICE_AUTHENTICATED, {"deviceId": device_id})
            self._flush_offline_queue(device_id)
        return ok

    def device_left(self, device_id: str):
        self.device_registry.mark_offline(device_id)
        self._publish(SyncEvent.DEVICE_LEFT, {"deviceId": device_id})
        logger.info(f"Device went offline: {device_id}")

    # ── Sync Operations ────────────────────────────────────────────────────────

    def sync_now(self, target_device_id: Optional[str] = None) -> bool:
        targets = ([self.device_registry.get(target_device_id)]
                   if target_device_id
                   else self.device_registry.get_online())
        targets = [t for t in targets if t and t.is_authenticated]

        payloads = self.sync_engine.build_outbound_payloads()

        if not targets:
            logger.info("No online devices — queuing payloads offline")
            for p in payloads:
                self.repository.enqueue(p)
            return False

        self._publish(SyncEvent.SYNC_STARTED, {"targets": len(targets)})
        success = True

        for target in targets:
            try:
                for payload in payloads:
                    logger.debug(f"→ Sent [{payload.category.value}] {payload.key} to '{target.device_name}'")
                    self._total_sent += 1
                logger.info(f"Sync → '{target.device_name}' ({len(payloads)} payloads)")
            except Exception as e:
                logger.error(f"Sync failed → '{target.device_name}': {e}", exc_info=True)
                for p in payloads:
                    self.repository.enqueue(p)
                success = False

        self._last_sync_timestamp = time.time()
        self._publish(SyncEvent.SYNC_COMPLETED if success else SyncEvent.SYNC_FAILED,
                      {"payloads": len(payloads), "targets": len(targets)})
        return success

    def receive_payload(self, payload: SyncPayload) -> bool:
        if not self.device_registry.is_authenticated(payload.source_device_id):
            logger.warning(f"REJECTED payload from unauthenticated device: {payload.source_device_id}")
            return False

        self._total_received += 1

        conflict = self.repository.detect_conflict(payload)
        if conflict:
            resolved = self.conflict_resolver.resolve(conflict, self.local_platform)
            self.repository.record_conflict(resolved)
            self._publish(SyncEvent.CONFLICT_DETECTED,
                          {"key": conflict.key, "category": conflict.category.value})
            if resolved.is_resolved:
                self._publish(SyncEvent.CONFLICT_RESOLVED,
                              {"key": conflict.key, "resolvedValue": resolved.resolved_value or ""})
                final_payload = SyncPayload(
                    category=payload.category,
                    key=payload.key,
                    value=resolved.resolved_value or payload.value,
                    source_device_id=payload.source_device_id,
                    timestamp=payload.timestamp
                )
                return self.sync_engine.apply_inbound(final_payload, self.repository)
            return False  # pending user confirmation

        return self.sync_engine.apply_inbound(payload, self.repository)

    # ── Session Continuity ─────────────────────────────────────────────────────

    def start_session(self, task_description: str) -> SyncSession:
        session = SyncSession(
            origin_device_id=self.local_device_id,
            current_device_id=self.local_device_id,
            task_description=task_description
        )
        self.repository.save_session(session)
        logger.info(f"Session started: '{task_description}' [{session.session_id}]")
        return session

    def handoff_session(self, session_id: str, target_device_id: str) -> bool:
        session = self.repository.get_session(session_id)
        if not session:
            return False
        session.current_device_id = target_device_id
        session.updated_at = time.time()
        self.repository.save_session(session)
        logger.info(f"Session '{session.task_description}' handed off → {target_device_id}")
        return True

    # ── Offline Queue ──────────────────────────────────────────────────────────

    def _flush_offline_queue(self, device_id: str):
        queued = self.repository.drain_queue()
        if not queued:
            return
        logger.info(f"Flushing {len(queued)} queued payloads to {device_id}")
        for payload in queued:
            logger.debug(f"→ Flushed [{payload.category.value}] {payload.key}")

    # ── Stats & Security ───────────────────────────────────────────────────────

    def get_stats(self) -> SyncStats:
        return SyncStats(
            total_payloads_sent=self._total_sent,
            total_payloads_received=self._total_received,
            total_conflicts_detected=len(self.repository.get_conflicts()),
            total_conflicts_resolved=sum(1 for c in self.repository.get_conflicts() if c.is_resolved),
            last_sync_timestamp=self._last_sync_timestamp,
            pending_queue_size=self.repository.queue_size(),
            connected_devices=self.device_registry.count_online()
        )

    def add_result_listener(self, listener: Callable):
        self._result_listeners.append(listener)

    def _publish(self, event: SyncEvent, payload: dict):
        if self._lifecycle_manager:
            self._lifecycle_manager.publish_event(event.value, payload)
