import sys
import os
import unittest
import time

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from nova.working_memory import WorkingMemory, WorkingMemoryState, BrowserInfo, MemoryEvent, Interaction

class TestWorkingMemory(unittest.TestCase):

    def setUp(self):
        self.wm = WorkingMemory()

    def test_initialization(self):
        """Verify that WorkingMemory starts in a clean default state."""
        self.assertIsInstance(self.wm.state, WorkingMemoryState)
        self.assertIsNone(self.wm.get("current_task"))
        self.assertIsNone(self.wm.get("current_goal"))
        self.assertEqual(self.wm.get("execution_status"), "idle")
        self.assertEqual(len(self.wm.state.timestamped_events), 0)
        self.assertEqual(len(self.wm.state.conversation_history), 0)

    def test_set_and_get_predefined_attributes(self):
        """Verify setting and getting predefined attributes updates the core state model."""
        self.wm.set("current_task", "Test Task")
        self.wm.set("current_goal", "Verify working memory")
        self.wm.set("execution_status", "running")
        self.wm.set("conversation_topic", "Cognitive architectures")
        
        self.assertEqual(self.wm.get("current_task"), "Test Task")
        self.assertEqual(self.wm.get("current_goal"), "Verify working memory")
        self.assertEqual(self.wm.get("execution_status"), "running")
        self.assertEqual(self.wm.get("conversation_topic"), "Cognitive architectures")

    def test_set_and_get_dynamic_properties(self):
        """Verify setting and getting non-predefined attributes falls back to additional_properties."""
        self.wm.set("future_planner_flag", True)
        self.wm.set("reasoning_depth", 4)
        
        self.assertEqual(self.wm.get("future_planner_flag"), True)
        self.assertEqual(self.wm.get("reasoning_depth"), 4)
        self.assertIn("future_planner_flag", self.wm.state.additional_properties)
        self.assertIn("reasoning_depth", self.wm.state.additional_properties)

    def test_remove_attributes_and_properties(self):
        """Verify removing keys correctly resets state attributes or deletes dynamic properties."""
        # Predefined attribute
        self.wm.set("current_task", "Clean code")
        self.wm.remove("current_task")
        self.assertIsNone(self.wm.get("current_task"))

        # Predefined dictionary attribute
        self.wm.set("conversation_context", {"user_locale": "en_US"})
        self.wm.remove("conversation_context")
        self.assertEqual(self.wm.get("conversation_context"), {})

        # Predefined status attribute
        self.wm.set("execution_status", "aborted")
        self.wm.remove("execution_status")
        self.assertEqual(self.wm.get("execution_status"), "idle")

        # Dynamic attribute
        self.wm.set("dynamic_key", "temporary_value")
        self.wm.remove("dynamic_key")
        self.assertIsNone(self.wm.get("dynamic_key"))
        self.assertNotIn("dynamic_key", self.wm.state.additional_properties)

    def test_append_history(self):
        """Verify appending to history works with both typed objects and raw dicts."""
        # Test appending dict
        self.wm.append_history({
            "user_prompt": "Hello Nova",
            "assistant_response": "Hello Boss",
            "intent": "greeting",
            "metadata": {"source": "voice"}
        })
        self.assertEqual(len(self.wm.state.conversation_history), 1)
        self.assertIsInstance(self.wm.state.conversation_history[0], Interaction)
        self.assertEqual(self.wm.state.conversation_history[0].user_prompt, "Hello Nova")

        # Test appending Interaction object
        self.wm.append_history(Interaction(
            user_prompt="Explain quantum physics",
            assistant_response="It is complex...",
            intent="explain"
        ))
        self.assertEqual(len(self.wm.state.conversation_history), 2)
        self.assertIsInstance(self.wm.state.conversation_history[1], Interaction)
        self.assertEqual(self.wm.state.conversation_history[1].user_prompt, "Explain quantum physics")

        # Test invalid type
        with self.assertRaises(TypeError):
            self.wm.append_history("invalid history record")

    def test_timestamped_events(self):
        """Verify memory events can be added with structured metadata."""
        evt = MemoryEvent(event_type="reasoning_step", message="Thinking about browser tabs", metadata={"tabs_found": 3})
        self.wm.state.timestamped_events.append(evt)
        self.assertEqual(len(self.wm.state.timestamped_events), 1)
        self.assertEqual(self.wm.state.timestamped_events[0].event_type, "reasoning_step")
        self.assertEqual(self.wm.state.timestamped_events[0].metadata["tabs_found"], 3)

    def test_snapshot_and_restore(self):
        """Verify structured states can be serialized to snapshots and perfectly restored to typed models."""
        self.wm.set("current_task", "Serialization checklist")
        self.wm.set("browser_information", BrowserInfo(
            active_tab_url="https://example.com",
            active_tab_title="Example Site",
            open_tabs_count=2
        ))
        self.wm.append_history({
            "user_prompt": "Snapshot trigger",
            "assistant_response": "Staging...",
            "intent": "testing"
        })
        self.wm.set("dynamic_option", 42)

        # Create snapshot
        snap = self.wm.snapshot()
        self.assertIsInstance(snap, dict)
        self.assertEqual(snap["current_task"], "Serialization checklist")
        self.assertEqual(snap["browser_information"]["active_tab_url"], "https://example.com")
        self.assertEqual(snap["additional_properties"]["dynamic_option"], 42)

        # Mutate current memory state
        self.wm.set("current_task", "Mutated task")
        self.wm.set("browser_information", None)
        self.wm.clear()

        # Restore from snapshot
        self.wm.restore(snap)
        self.assertEqual(self.wm.get("current_task"), "Serialization checklist")
        self.assertEqual(self.wm.get("dynamic_option"), 42)
        
        # Verify typed reconstruction of nested BrowserInfo
        browser_info = self.wm.get("browser_information")
        self.assertIsInstance(browser_info, BrowserInfo)
        self.assertEqual(browser_info.active_tab_url, "https://example.com")
        self.assertEqual(browser_info.active_tab_title, "Example Site")
        
        # Verify typed reconstruction of interaction history
        history = self.wm.get("conversation_history")
        self.assertEqual(len(history), 1)
        self.assertIsInstance(history[0], Interaction)
        self.assertEqual(history[0].user_prompt, "Snapshot trigger")

    def test_clear_and_reset(self):
        """Verify clear and reset wipe both attributes and dynamic properties."""
        self.wm.set("current_task", "Testing clear")
        self.wm.set("custom_property", "Wipe me")
        
        self.wm.clear()
        self.assertIsNone(self.wm.get("current_task"))
        self.assertIsNone(self.wm.get("custom_property"))
        self.assertEqual(len(self.wm.state.additional_properties), 0)

        # Test reset
        self.wm.set("current_task", "Testing reset")
        self.wm.set("custom_property", "Wipe me again")
        self.wm.reset()
        self.assertIsNone(self.wm.get("current_task"))
        self.assertIsNone(self.wm.get("custom_property"))

    def test_restore_invalid_type(self):
        """Verify restore raises exception on invalid input formats."""
        with self.assertRaises(ValueError):
            self.wm.restore("not a dictionary")

if __name__ == "__main__":
    unittest.main()
