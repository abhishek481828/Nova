"""Nova v3.0 Phase 8 Automated Test Suite: Multi-Device Synchronization."""

import time
import pytest
from nova.mobile.sync.enums import (
    Platform, DeviceStatus, ConflictPolicy, SyncEvent, SyncCategory
)
from nova.mobile.sync.models import (
    DeviceInfo, SyncPayload, SyncConflict, SyncSession, BLOCKED_SYNC_KEYS
)
from nova.mobile.sync.device_registry import DeviceRegistry
from nova.mobile.sync.conflict_resolver import ConflictResolver
from nova.mobile.sync.repository import SyncRepository
from nova.mobile.sync.sync_engine import SyncEngine
from nova.mobile.sync.manager import SyncManager
from nova.mobile.lifecycle import LifecycleManager


# ─── Helpers ─────────────────────────────────────────────────────────────────

def make_device(device_id="phone-001", name="Nova Phone",
                platform=Platform.ANDROID, authenticated=False) -> DeviceInfo:
    return DeviceInfo(
        device_id=device_id, device_name=name,
        platform=platform, version="3.0.0",
        is_authenticated=authenticated,
        status=DeviceStatus.ONLINE if authenticated else DeviceStatus.UNAUTHENTICATED
    )


def make_payload(key="preferred_brightness", value="70",
                 device_id="phone-001", category=SyncCategory.PREFERENCES,
                 timestamp=None) -> SyncPayload:
    return SyncPayload(
        category=category, key=key, value=value,
        source_device_id=device_id,
        timestamp=timestamp or time.time()
    )


def make_manager(device_id="phone-001", name="Nova Phone",
                 platform=Platform.ANDROID,
                 policy=ConflictPolicy.NEWEST_WINS,
                 lifecycle=None) -> SyncManager:
    engine = SyncEngine(device_id=device_id)
    return SyncManager(
        local_device_id=device_id,
        local_device_name=name,
        local_platform=platform,
        sync_engine=engine,
        lifecycle_manager=lifecycle,
        conflict_policy=policy
    )


# ─── DeviceInfo Tests ─────────────────────────────────────────────────────────

def test_device_info_created():
    d = make_device()
    assert d.device_id == "phone-001"
    assert d.platform == Platform.ANDROID
    assert d.is_authenticated is False


def test_sync_payload_checksum_auto_computed():
    p = make_payload()
    assert len(p.checksum) == 16


def test_sync_payload_integrity_passes():
    p = make_payload(value="60")
    assert p.verify_integrity() is True


def test_sync_payload_integrity_tampered():
    p = make_payload(value="60")
    p.checksum = "aaaaaaaaaaaaaaaa"  # tampered
    assert p.verify_integrity() is False


def test_sync_payload_sensitive_key_blocked():
    p = make_payload(key="password")
    assert p.is_sensitive() is True


def test_sync_payload_normal_key_not_sensitive():
    p = make_payload(key="preferred_brightness")
    assert p.is_sensitive() is False


# ─── DeviceRegistry Tests ─────────────────────────────────────────────────────

def test_device_registry_register():
    reg = DeviceRegistry()
    d = make_device()
    assert reg.register(d) is True
    assert reg.get("phone-001") is not None


def test_device_registry_authenticate():
    reg = DeviceRegistry()
    d = make_device()
    reg.register(d)
    assert reg.authenticate("phone-001") is True
    assert reg.get("phone-001").is_authenticated is True


def test_device_registry_unauthenticated_not_in_authenticated_list():
    reg = DeviceRegistry()
    reg.register(make_device("a", authenticated=False))
    assert len(reg.get_authenticated()) == 0


def test_device_registry_revoke():
    reg = DeviceRegistry()
    d = make_device(authenticated=True)
    reg.register(d)
    reg.authenticate(d.device_id)
    reg.revoke(d.device_id)
    assert reg.get(d.device_id).is_authenticated is False


def test_device_registry_mark_offline():
    reg = DeviceRegistry()
    d = make_device()
    reg.register(d)
    reg.authenticate(d.device_id)
    reg.mark_offline(d.device_id)
    assert reg.get(d.device_id).status == DeviceStatus.OFFLINE


def test_device_registry_remove():
    reg = DeviceRegistry()
    d = make_device()
    reg.register(d)
    assert reg.remove(d.device_id) is True
    assert reg.get(d.device_id) is None


def test_device_registry_audit_log_populated():
    reg = DeviceRegistry()
    d = make_device()
    reg.register(d)
    reg.authenticate(d.device_id)
    assert len(reg.get_audit_log()) >= 2


def test_device_registry_count():
    reg = DeviceRegistry()
    reg.register(make_device("a"))
    reg.register(make_device("b"))
    assert reg.count() == 2


# ─── ConflictResolver Tests ───────────────────────────────────────────────────

def test_conflict_resolver_newest_wins_remote():
    cr = ConflictResolver(ConflictPolicy.NEWEST_WINS)
    now = time.time()
    conflict = SyncConflict(
        category=SyncCategory.PREFERENCES, key="brightness",
        local_value="60", remote_value="80",
        local_timestamp=now - 10, remote_timestamp=now,
        local_device_id="phone", remote_device_id="laptop"
    )
    resolved = cr.resolve(conflict, Platform.ANDROID)
    assert resolved.is_resolved is True
    assert resolved.resolved_value == "80"  # remote is newer


def test_conflict_resolver_newest_wins_local():
    cr = ConflictResolver(ConflictPolicy.NEWEST_WINS)
    now = time.time()
    conflict = SyncConflict(
        category=SyncCategory.PREFERENCES, key="volume",
        local_value="50", remote_value="75",
        local_timestamp=now, remote_timestamp=now - 10,
        local_device_id="phone", remote_device_id="laptop"
    )
    resolved = cr.resolve(conflict, Platform.ANDROID)
    assert resolved.resolved_value == "50"  # local is newer


def test_conflict_resolver_phone_wins():
    cr = ConflictResolver(ConflictPolicy.PHONE_WINS)
    conflict = SyncConflict(
        category=SyncCategory.PREFERENCES, key="brightness",
        local_value="60", remote_value="80",
        local_timestamp=0, remote_timestamp=1,
        local_device_id="phone", remote_device_id="laptop"
    )
    resolved = cr.resolve(conflict, Platform.ANDROID)
    assert resolved.resolved_value == "60"  # local phone wins


def test_conflict_resolver_nova_core_wins():
    cr = ConflictResolver(ConflictPolicy.NOVA_CORE_WINS)
    conflict = SyncConflict(
        category=SyncCategory.PREFERENCES, key="brightness",
        local_value="60", remote_value="80",
        local_timestamp=0, remote_timestamp=1,
        local_device_id="laptop", remote_device_id="phone"
    )
    resolved = cr.resolve(conflict, Platform.NOVA_CORE)
    assert resolved.resolved_value == "60"  # local nova_core wins


def test_conflict_resolver_user_confirm_queues():
    cr = ConflictResolver(ConflictPolicy.USER_CONFIRM)
    conflict = SyncConflict(
        category=SyncCategory.PREFERENCES, key="brightness",
        local_value="60", remote_value="80",
        local_timestamp=0, remote_timestamp=1,
        local_device_id="phone", remote_device_id="laptop"
    )
    resolved = cr.resolve(conflict, Platform.ANDROID)
    assert resolved.is_resolved is False
    assert cr.pending_count() == 1


def test_conflict_resolver_user_resolve():
    cr = ConflictResolver(ConflictPolicy.USER_CONFIRM)
    conflict = SyncConflict(
        category=SyncCategory.PREFERENCES, key="vol",
        local_value="50", remote_value="75",
        local_timestamp=0, remote_timestamp=1,
        local_device_id="phone", remote_device_id="laptop"
    )
    cr.resolve(conflict, Platform.ANDROID)
    resolved = cr.resolve_by_user(conflict.conflict_id, "60")
    assert resolved is not None
    assert resolved.resolved_value == "60"
    assert cr.pending_count() == 0


def test_conflict_resolver_blocks_sensitive_keys():
    cr = ConflictResolver(ConflictPolicy.NEWEST_WINS)
    conflict = SyncConflict(
        category=SyncCategory.PREFERENCES, key="password",
        local_value="secret1", remote_value="secret2",
        local_timestamp=0, remote_timestamp=1,
        local_device_id="phone", remote_device_id="laptop"
    )
    resolved = cr.resolve(conflict, Platform.ANDROID)
    assert resolved.is_resolved is False


# ─── SyncRepository Tests ─────────────────────────────────────────────────────

def test_repository_put_and_get():
    repo = SyncRepository()
    p = make_payload()
    assert repo.put(p) is True
    assert repo.get(SyncCategory.PREFERENCES, "preferred_brightness") is not None


def test_repository_newer_overwrites_older():
    repo = SyncRepository()
    now = time.time()
    p_old = make_payload(value="60", timestamp=now - 100)
    p_new = make_payload(value="80", timestamp=now)
    repo.put(p_old)
    repo.put(p_new)
    result = repo.get(SyncCategory.PREFERENCES, "preferred_brightness")
    assert result.value == "80"


def test_repository_older_does_not_overwrite():
    repo = SyncRepository()
    now = time.time()
    p_new = make_payload(value="80", timestamp=now)
    p_old = make_payload(value="60", timestamp=now - 100)
    repo.put(p_new)
    result_before = repo.put(p_old)
    assert result_before is False
    assert repo.get(SyncCategory.PREFERENCES, "preferred_brightness").value == "80"


def test_repository_detect_conflict():
    repo = SyncRepository()
    now = time.time()
    existing = make_payload(value="60", device_id="phone", timestamp=now - 5)
    repo.put(existing)
    incoming = make_payload(value="80", device_id="laptop", timestamp=now)
    conflict = repo.detect_conflict(incoming)
    assert conflict is not None
    assert conflict.local_value == "60"
    assert conflict.remote_value == "80"


def test_repository_no_conflict_same_value():
    repo = SyncRepository()
    p = make_payload(value="70")
    repo.put(p)
    same = make_payload(value="70", device_id="laptop")
    assert repo.detect_conflict(same) is None


def test_repository_offline_queue():
    repo = SyncRepository()
    p = make_payload()
    repo.enqueue(p)
    assert repo.queue_size() == 1
    drained = repo.drain_queue()
    assert len(drained) == 1
    assert repo.queue_size() == 0


def test_repository_conflict_history():
    repo = SyncRepository()
    c = SyncConflict(
        category=SyncCategory.PREFERENCES, key="vol",
        local_value="50", remote_value="70",
        local_timestamp=0, remote_timestamp=1,
        local_device_id="a", remote_device_id="b"
    )
    repo.record_conflict(c)
    assert len(repo.get_conflicts()) == 1
    assert len(repo.get_unresolved()) == 1


def test_repository_session_lifecycle():
    repo = SyncRepository()
    session = SyncSession(
        origin_device_id="phone", current_device_id="phone",
        task_description="Edit document"
    )
    repo.save_session(session)
    assert repo.get_session(session.session_id) is not None
    assert len(repo.get_active_sessions()) == 1
    repo.close_session(session.session_id)
    assert len(repo.get_active_sessions()) == 0


# ─── SyncEngine Tests ─────────────────────────────────────────────────────────

def test_sync_engine_blocks_sensitive_inbound():
    engine = SyncEngine(device_id="phone")
    repo = SyncRepository()
    p = make_payload(key="password", value="hunter2")
    result = engine.apply_inbound(p, repo)
    assert result is False


def test_sync_engine_integrity_failure_blocked():
    engine = SyncEngine(device_id="phone")
    repo = SyncRepository()
    p = make_payload(value="safe_value")
    p.checksum = "bad_checksum_123"
    result = engine.apply_inbound(p, repo)
    assert result is False


def test_sync_engine_valid_payload_accepted():
    engine = SyncEngine(device_id="phone")
    repo = SyncRepository()
    p = make_payload(value="safe_value")
    result = engine.apply_inbound(p, repo)
    assert result is True


# ─── SyncManager Integration Tests ────────────────────────────────────────────

def test_sync_manager_start_registers_self():
    mgr = make_manager()
    mgr.start()
    own = mgr.device_registry.get("phone-001")
    assert own is not None
    assert own.is_authenticated is True
    mgr.stop()


def test_sync_manager_register_and_authenticate_device():
    mgr = make_manager()
    mgr.start()
    laptop = make_device("laptop-001", "Nova Laptop", Platform.NOVA_CORE)
    assert mgr.register_device(laptop) is True
    assert mgr.authenticate_device("laptop-001") is True
    assert mgr.device_registry.get("laptop-001").is_authenticated is True
    mgr.stop()


def test_sync_manager_reject_unauthenticated_payload():
    mgr = make_manager()
    mgr.start()
    p = make_payload(device_id="unknown-device")
    result = mgr.receive_payload(p)
    assert result is False
    mgr.stop()


def test_sync_manager_accept_authenticated_payload():
    mgr = make_manager()
    mgr.start()
    laptop = make_device("laptop-001", "Laptop", Platform.NOVA_CORE, authenticated=True)
    mgr.register_device(laptop)
    mgr.authenticate_device("laptop-001")
    p = make_payload(value="65", device_id="laptop-001")
    result = mgr.receive_payload(p)
    assert result is True
    mgr.stop()


def test_sync_manager_conflict_resolved_newest_wins():
    mgr = make_manager(policy=ConflictPolicy.NEWEST_WINS)
    mgr.start()
    laptop = make_device("laptop-001", "Laptop", Platform.NOVA_CORE, authenticated=True)
    mgr.register_device(laptop)
    mgr.authenticate_device("laptop-001")

    now = time.time()
    # Store an older local value
    local_p = make_payload(value="60", device_id="phone-001", timestamp=now - 10)
    mgr.repository.put(local_p)

    # Receive a newer remote value
    remote_p = make_payload(value="80", device_id="laptop-001", timestamp=now)
    mgr.receive_payload(remote_p)

    conflicts = mgr.repository.get_conflicts()
    assert len(conflicts) == 1
    assert conflicts[0].is_resolved is True
    assert conflicts[0].resolved_value == "80"
    mgr.stop()


def test_sync_manager_offline_queue_flushed_on_auth():
    mgr = make_manager()
    mgr.start()
    # Queue a payload when no devices online
    p = make_payload()
    mgr.repository.enqueue(p)
    assert mgr.repository.queue_size() == 1

    # Authenticate a device → flush
    laptop = make_device("laptop-001", "Laptop", Platform.NOVA_CORE)
    mgr.register_device(laptop)
    mgr.authenticate_device("laptop-001")
    assert mgr.repository.queue_size() == 0
    mgr.stop()


def test_sync_manager_session_continuity():
    mgr = make_manager()
    mgr.start()
    session = mgr.start_session("Edit document")
    assert session is not None
    assert session.origin_device_id == "phone-001"
    assert mgr.repository.get_session(session.session_id) is not None

    result = mgr.handoff_session(session.session_id, "laptop-001")
    assert result is True
    updated = mgr.repository.get_session(session.session_id)
    assert updated.current_device_id == "laptop-001"
    mgr.stop()


def test_sync_manager_stats():
    mgr = make_manager()
    mgr.start()
    stats = mgr.get_stats()
    assert stats.total_payloads_sent == 0
    assert stats.connected_devices == 1  # self
    mgr.stop()


# ─── Event Tests ──────────────────────────────────────────────────────────────

def test_sync_events_published():
    lm = LifecycleManager()
    lm.initialize()
    mgr = make_manager(lifecycle=lm)
    mgr.start()

    laptop = make_device("laptop-001", "Laptop", Platform.NOVA_CORE)
    mgr.register_device(laptop)
    mgr.authenticate_device("laptop-001")
    mgr.device_left("laptop-001")

    event_names = [e.event_name for e in lm.get_event_history()]
    assert SyncEvent.SYNC_RESTORED.value in event_names
    assert SyncEvent.DEVICE_JOINED.value in event_names
    assert SyncEvent.DEVICE_AUTHENTICATED.value in event_names
    assert SyncEvent.DEVICE_LEFT.value in event_names
    mgr.stop()


# ─── Security Tests ───────────────────────────────────────────────────────────

def test_sensitive_keys_never_synced():
    for key in ["password", "auth_token", "otp", "private_key", "cvv"]:
        p = SyncPayload(category=SyncCategory.PREFERENCES, key=key,
                        value="should_not_sync", source_device_id="x")
        assert p.is_sensitive() is True


def test_only_authenticated_devices_can_send_payloads():
    mgr = make_manager()
    mgr.start()
    p = make_payload(device_id="rogue-device")
    assert mgr.receive_payload(p) is False
    mgr.stop()


# ─── Error Handling Tests ──────────────────────────────────────────────────────

def test_handoff_nonexistent_session():
    mgr = make_manager()
    mgr.start()
    assert mgr.handoff_session("nonexistent-id", "laptop") is False
    mgr.stop()


def test_authenticate_unknown_device():
    mgr = make_manager()
    mgr.start()
    assert mgr.authenticate_device("nonexistent") is False
    mgr.stop()
