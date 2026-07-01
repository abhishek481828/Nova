import unittest
from unittest.mock import MagicMock, patch
import time

from nova.working_memory import WorkingMemory, HistoryEntry, Interaction
from nova.actions.base import BaseAction
from nova.browser_manager import BrowserManager

# Dummy Action
class DummyHistoryAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "dummy_history_action"

    def execute(self, params: dict) -> str:
        return "success"

class TestHistoryMemory(unittest.TestCase):
    def setUp(self):
        # Configure History Manager with a limit of 3 for testing sliding window
        self.wm = WorkingMemory(history_limit=3)
        self.hm = self.wm.history_manager

    def tearDown(self):
        BaseAction._shared_working_memory = None
        BrowserManager._working_memory = None

    def test_validation_constraints(self):
        entry = HistoryEntry(event_type="system_event", message="test")
        self.wm.set("history_entries", [entry])
        self.assertEqual(len(self.wm.get("history_entries")), 1)

        # Invalid type raises TypeError
        with self.assertRaises(TypeError):
            self.wm.set("history_entries", "not-a-list")

        with self.assertRaises(TypeError):
            self.wm.set("history_entries", ["not-an-entry"])

    def test_history_addition_and_limit(self):
        # Add 3 entries (reaches limit)
        self.hm.add_entry("system_event", "Msg 1")
        self.hm.add_entry("system_event", "Msg 2")
        self.hm.add_entry("system_event", "Msg 3")

        entries = self.hm.get_entries()
        self.assertEqual(len(entries), 3)
        self.assertEqual(entries[0].message, "Msg 1")
        self.assertEqual(entries[2].message, "Msg 3")

        # Add 4th entry (should pop Msg 1)
        self.hm.add_entry("system_event", "Msg 4")
        
        entries_after = self.hm.get_entries()
        self.assertEqual(len(entries_after), 3)
        self.assertEqual(entries_after[0].message, "Msg 2")
        self.assertEqual(entries_after[2].message, "Msg 4")

    def test_filtering_by_event_type(self):
        self.hm.add_entry("system_event", "Sys 1")
        self.hm.add_entry("browser_event", "Browse 1")
        self.hm.add_entry("system_event", "Sys 2")

        sys_entries = self.hm.get_entries("system_event")
        self.assertEqual(len(sys_entries), 2)
        self.assertEqual(sys_entries[0].message, "Sys 1")
        self.assertEqual(sys_entries[1].message, "Sys 2")

        browse_entries = self.hm.get_entries("browser_event")
        self.assertEqual(len(browse_entries), 1)
        self.assertEqual(browse_entries[0].message, "Browse 1")

    def test_append_history_auto_tracking(self):
        self.wm.append_history({
            "user_prompt": "Hello",
            "assistant_response": "Hi",
            "intent": "greet"
        })

        recent = self.hm.get_entries()
        # Should record two entries: user_interaction and assistant_response
        self.assertEqual(len(recent), 2)
        self.assertEqual(recent[0].event_type, "user_interaction")
        self.assertEqual(recent[0].message, "User: Hello")
        self.assertEqual(recent[1].event_type, "assistant_response")
        self.assertEqual(recent[1].message, "Assistant: Hi")

    def test_action_execution_auto_tracking(self):
        action = DummyHistoryAction()
        action.execute({})

        recent = self.hm.get_entries()
        self.assertEqual(len(recent), 1)
        self.assertEqual(recent[0].event_type, "action_execution")
        self.assertIn("dummy_history_action", recent[0].message)

    @patch("nova.browser_manager.BrowserManager.is_browser_running")
    @patch("nova.browser_manager.BrowserManager.get_browser")
    def test_browser_events_auto_tracking(self, mock_get_browser, mock_is_running):
        mock_is_running.return_value = True
        BrowserManager._working_memory = self.wm

        # Mock Page
        mock_page = MagicMock()
        mock_page.title.return_value = "Search Page"
        mock_page.url = "https://google.com"

        # Mock Context
        mock_context = MagicMock()
        mock_context.pages = [mock_page]

        # Mock Browser
        mock_browser = MagicMock()
        mock_browser.contexts = [mock_context]
        mock_get_browser.return_value = mock_browser

        # Run navigation state update
        BrowserManager.update_browser_memory_state(self.wm)
        
        # Verify navigation event recorded in history
        browse_entries = self.hm.get_entries("browser_event")
        self.assertEqual(len(browse_entries), 1)
        self.assertIn("navigated to: https://google.com", browse_entries[0].message)

        # Trigger download event
        mock_download = MagicMock()
        mock_download.url = "https://example.com/app.dmg"
        mock_download.suggested_filename = "app.dmg"

        BrowserManager._handle_download(mock_download)
        
        # Verify download event recorded in history
        browse_entries_updated = self.hm.get_entries("browser_event")
        self.assertEqual(len(browse_entries_updated), 2)
        self.assertIn("download initiated: app.dmg", browse_entries_updated[1].message)

    def test_snapshot_and_restore(self):
        self.hm.add_entry("system_event", "Msg 1")
        self.hm.add_entry("voice_event", "Msg 2")

        snap = self.wm.snapshot()
        self.assertEqual(snap["history_entries"][0]["message"], "Msg 1")
        self.assertEqual(snap["history_entries"][1]["event_type"], "voice_event")

        # Mutate
        self.wm.clear()
        self.assertEqual(len(self.hm.get_entries()), 0)

        # Restore
        self.wm.restore(snap)
        entries = self.hm.get_entries()
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0].message, "Msg 1")
        self.assertEqual(entries[1].event_type, "voice_event")
        self.assertIsInstance(entries[0], HistoryEntry)

if __name__ == "__main__":
    unittest.main()
