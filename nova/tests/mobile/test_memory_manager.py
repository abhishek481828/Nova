"""Nova v3.0 Phase 6 Automated Test Suite: Personal Memory & User Intelligence."""

import pytest
from nova.mobile.memory.enums import MemoryCategory, MemoryEvent
from nova.mobile.memory.entry import MemoryEntry, BLOCKED_KEYS
from nova.mobile.memory.store import MemoryStore
from nova.mobile.memory.repository import MemoryRepository
from nova.mobile.memory.config import MemoryConfiguration, MemoryStatistics
from nova.mobile.memory.manager import MemoryManager
from nova.mobile.lifecycle import LifecycleManager


# ─── MemoryEntry Tests ────────────────────────────────────────────────────────

def test_memory_entry_basic():
    entry = MemoryEntry(
        category=MemoryCategory.FAVORITE_CONTACT,
        key="pankaj",
        value="Pankaj"
    )
    assert entry.category == MemoryCategory.FAVORITE_CONTACT
    assert entry.key == "pankaj"
    assert entry.value == "Pankaj"
    assert entry.confidence == 1.0
    assert entry.is_user_deletable is True
    assert entry.is_user_editable is True


def test_memory_entry_sensitive_key_detection():
    entry = MemoryEntry(
        category=MemoryCategory.USER_PREFERENCE,
        key="password",
        value="hunter2"
    )
    assert entry.is_sensitive() is True


def test_memory_entry_normal_key_not_sensitive():
    entry = MemoryEntry(
        category=MemoryCategory.PREFERRED_BRIGHTNESS,
        key="preferred_brightness",
        value="70"
    )
    assert entry.is_sensitive() is False


# ─── MemoryStore Tests ────────────────────────────────────────────────────────

def test_memory_store_put_and_get():
    store = MemoryStore()
    entry = MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "pankaj", "Pankaj")
    assert store.put(entry) is True
    result = store.get(MemoryCategory.FAVORITE_CONTACT, "pankaj")
    assert result is not None
    assert result.value == "Pankaj"


def test_memory_store_blocks_sensitive_keys():
    store = MemoryStore()
    entry = MemoryEntry(MemoryCategory.USER_PREFERENCE, "password", "hunter2")
    assert store.put(entry) is False
    assert store.get(MemoryCategory.USER_PREFERENCE, "password") is None


def test_memory_store_frequency_increment():
    store = MemoryStore()
    entry = MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "pankaj", "Pankaj", frequency=1)
    store.put(entry)
    store.put(entry)  # second put → frequency increments
    result = store.get(MemoryCategory.FAVORITE_CONTACT, "pankaj")
    assert result.frequency == 2


def test_memory_store_search():
    store = MemoryStore()
    store.put(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "pankaj", "Pankaj"))
    store.put(MemoryEntry(MemoryCategory.FAVORITE_APP, "youtube", "YouTube"))
    results = store.search("pankaj")
    assert len(results) == 1
    assert results[0].value == "Pankaj"


def test_memory_store_delete():
    store = MemoryStore()
    store.put(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "pankaj", "Pankaj"))
    assert store.delete(MemoryCategory.FAVORITE_CONTACT, "pankaj") is True
    assert store.get(MemoryCategory.FAVORITE_CONTACT, "pankaj") is None


def test_memory_store_clear():
    store = MemoryStore()
    store.put(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "pankaj", "Pankaj"))
    store.put(MemoryEntry(MemoryCategory.FAVORITE_APP, "youtube", "YouTube"))
    count = store.clear()
    assert count == 2
    assert store.total_count() == 0


# ─── MemoryRepository Tests ───────────────────────────────────────────────────

def test_repository_save_and_list():
    repo = MemoryRepository(MemoryStore())
    repo.save(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "ravi", "Ravi"))
    repo.save(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "priya", "Priya"))
    contacts = repo.list(MemoryCategory.FAVORITE_CONTACT)
    assert len(contacts) == 2


def test_repository_export_and_import():
    store = MemoryStore()
    repo = MemoryRepository(store)
    repo.save(MemoryEntry(MemoryCategory.PREFERRED_BRIGHTNESS, "preferred_brightness", "70"))

    exported = repo.export()
    assert len(exported) == 1
    assert exported[0]["key"] == "preferred_brightness"

    # Import into fresh repo
    new_repo = MemoryRepository(MemoryStore())
    records = [MemoryEntry(
        category=MemoryCategory(e["category"]),
        key=e["key"],
        value=e["value"]
    ) for e in exported]
    count = new_repo.import_records(records)
    assert count == 1


def test_repository_get_statistics():
    repo = MemoryRepository(MemoryStore())
    repo.save(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "pankaj", "Pankaj"))
    repo.save(MemoryEntry(MemoryCategory.FAVORITE_APP, "youtube", "YouTube"))
    stats = repo.get_statistics()
    assert stats.total_entries == 2
    assert stats.favorite_contacts_count == 1
    assert stats.favorite_apps_count == 1


def test_repository_delete_category():
    repo = MemoryRepository(MemoryStore())
    repo.save(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "a", "A"))
    repo.save(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "b", "B"))
    count = repo.delete_category(MemoryCategory.FAVORITE_CONTACT)
    assert count == 2
    assert len(repo.list(MemoryCategory.FAVORITE_CONTACT)) == 0


# ─── MemoryManager Learning Tests ────────────────────────────────────────────

def test_memory_manager_learns_favorite_contact():
    config = MemoryConfiguration(contact_frequency_threshold=3)
    mgr = MemoryManager(config=config)

    for _ in range(3):
        mgr.on_command_executed("CALL_CONTACT", {"contact_name": "Pankaj"}, "Call Pankaj")

    result = mgr.store.get(MemoryCategory.FAVORITE_CONTACT, "pankaj")
    assert result is not None
    assert result.value == "Pankaj"


def test_memory_manager_does_not_learn_below_threshold():
    config = MemoryConfiguration(contact_frequency_threshold=5)
    mgr = MemoryManager(config=config)

    for _ in range(4):
        mgr.on_command_executed("CALL_CONTACT", {"contact_name": "Ravi"}, "Call Ravi")

    result = mgr.store.get(MemoryCategory.FAVORITE_CONTACT, "ravi")
    assert result is None


def test_memory_manager_learns_preferred_brightness():
    config = MemoryConfiguration(preference_repeat_threshold=3)
    mgr = MemoryManager(config=config)

    for pct in [70, 65, 72]:
        mgr.on_command_executed("SET_BRIGHTNESS", {"percentage": str(pct)}, f"Set brightness to {pct}")

    result = mgr.store.get(MemoryCategory.PREFERRED_BRIGHTNESS, "preferred_brightness")
    assert result is not None
    avg = int((70 + 65 + 72) / 3)
    assert abs(int(result.value) - avg) <= 1  # allow small rounding


def test_memory_manager_learns_preferred_volume():
    config = MemoryConfiguration(preference_repeat_threshold=3)
    mgr = MemoryManager(config=config)

    for pct in [60, 65, 60]:
        mgr.on_command_executed("SET_VOLUME", {"percentage": str(pct)}, f"Set volume to {pct}")

    result = mgr.store.get(MemoryCategory.PREFERRED_VOLUME, "preferred_volume")
    assert result is not None


def test_memory_manager_tracks_recent_commands():
    mgr = MemoryManager()
    mgr.on_command_executed("CALL_CONTACT", {"contact_name": "X"}, "Call X")
    recent = mgr.repository.list(MemoryCategory.RECENT_COMMAND)
    assert len(recent) >= 1


# ─── Memory Query Tests ───────────────────────────────────────────────────────

def test_memory_query_recall():
    mgr = MemoryManager()
    mgr.on_command_executed("CALL_CONTACT", {"contact_name": "Pankaj"},
                            "Call Pankaj")
    # Manually save a favorite to test recall
    mgr.repository.save(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "pankaj", "Pankaj"))

    response = mgr.handle_memory_query("What do you remember about me?")
    assert response is not None
    assert "remember" in response.lower()


def test_memory_query_forget_all():
    mgr = MemoryManager()
    mgr.repository.save(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "pankaj", "Pankaj"))
    mgr.repository.save(MemoryEntry(MemoryCategory.FAVORITE_APP, "youtube", "YouTube"))

    response = mgr.handle_memory_query("Forget everything")
    assert response is not None
    assert "cleared" in response.lower() or "2" in response
    assert mgr.store.total_count() == 0


def test_memory_query_forget_contacts():
    mgr = MemoryManager()
    mgr.repository.save(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "pankaj", "Pankaj"))

    response = mgr.handle_memory_query("Forget my favorite contacts")
    assert response is not None
    assert len(mgr.repository.list(MemoryCategory.FAVORITE_CONTACT)) == 0


def test_memory_query_returns_none_for_non_query():
    mgr = MemoryManager()
    response = mgr.handle_memory_query("Call Pankaj")
    assert response is None


# ─── Privacy Tests ────────────────────────────────────────────────────────────

def test_privacy_blocks_password_storage():
    mgr = MemoryManager()
    entry = MemoryEntry(MemoryCategory.USER_PREFERENCE, "password", "secret123")
    assert mgr.repository.save(entry) is False


def test_privacy_blocks_token_storage():
    mgr = MemoryManager()
    entry = MemoryEntry(MemoryCategory.USER_PREFERENCE, "auth_token", "tok_abc123")
    assert mgr.repository.save(entry) is False


def test_privacy_blocks_otp_storage():
    mgr = MemoryManager()
    entry = MemoryEntry(MemoryCategory.USER_PREFERENCE, "otp_code", "123456")
    assert mgr.repository.save(entry) is False


# ─── Event Publishing Tests ───────────────────────────────────────────────────

def test_memory_events_published_on_learn():
    lm = LifecycleManager()
    lm.initialize()
    config = MemoryConfiguration(contact_frequency_threshold=2)
    mgr = MemoryManager(config=config, lifecycle_manager=lm)

    for _ in range(2):
        mgr.on_command_executed("CALL_CONTACT", {"contact_name": "Ravi"}, "Call Ravi")

    event_names = [e.event_name for e in lm.get_event_history()]
    assert "MemoryCreated" in event_names or "MemoryUpdated" in event_names


def test_memory_events_published_on_clear():
    lm = LifecycleManager()
    lm.initialize()
    mgr = MemoryManager(lifecycle_manager=lm)
    mgr.repository.save(MemoryEntry(MemoryCategory.FAVORITE_CONTACT, "pankaj", "Pankaj"))
    mgr.handle_memory_query("Forget everything")

    event_names = [e.event_name for e in lm.get_event_history()]
    assert "MemoryCleared" in event_names


# ─── Sync Tests ───────────────────────────────────────────────────────────────

def test_sync_disabled_by_default():
    mgr = MemoryManager()
    result = mgr.sync_with_nova_core()
    assert result is False


def test_sync_enabled_when_configured():
    config = MemoryConfiguration(sync_with_nova_core=True)
    mgr = MemoryManager(config=config)
    result = mgr.sync_with_nova_core()
    assert result is True


# ─── Error Handling Tests ─────────────────────────────────────────────────────

def test_delete_nonexistent_entry_returns_false():
    mgr = MemoryManager()
    result = mgr.repository.delete(MemoryCategory.FAVORITE_CONTACT, "nonexistent_key")
    assert result is False


def test_clear_empty_store_returns_zero():
    mgr = MemoryManager()
    count = mgr.repository.clear()
    assert count == 0


def test_import_empty_list_returns_zero():
    mgr = MemoryManager()
    count = mgr.repository.import_records([])
    assert count == 0
