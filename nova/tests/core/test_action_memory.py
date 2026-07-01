import unittest
from typing import Dict, Any

from nova.core.memory import WorkingMemory
from nova.actions.base import BaseAction

# Test actions
class DummySuccessAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "dummy_success"

    def execute(self, params: Dict[str, Any]) -> str:
        return f"Hello, {params.get('name', 'World')}"

class DummyFailureAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "dummy_failure"

    def execute(self, params: Dict[str, Any]) -> str:
        raise ValueError(f"Failed operation: {params.get('reason', 'unknown')}")

class TestActionMemory(unittest.TestCase):
    def setUp(self):
        # Instantiate working memory which automatically sets BaseAction._shared_working_memory
        self.wm = WorkingMemory()
        self.success_action = DummySuccessAction()
        self.failure_action = DummyFailureAction()

    def tearDown(self):
        BaseAction._shared_working_memory = None

    def test_recent_actions_validation(self):
        # List of dicts should not throw
        self.wm.set("recent_actions", [{"action_name": "test"}])
        self.assertEqual(len(self.wm.get("recent_actions")), 1)

        # Invalid type should throw TypeError
        with self.assertRaises(TypeError):
            self.wm.set("recent_actions", "not-a-list")

        # Invalid item type should throw TypeError
        with self.assertRaises(TypeError):
            self.wm.set("recent_actions", ["not-a-dict"])

    def test_success_action_recording(self):
        params = {"name": "Nova User"}
        result = self.success_action.execute(params)
        
        self.assertEqual(result, "Hello, Nova User")

        # Check recorded actions in working memory
        recent = self.wm.get("recent_actions")
        self.assertEqual(len(recent), 1)
        record = recent[0]
        
        self.assertEqual(record["action_name"], "dummy_success")
        self.assertIn(record["category"], ("test_action_memory", "general")) # module name last part
        self.assertEqual(record["parameters"], params)
        self.assertEqual(record["result"], "Hello, Nova User")
        self.assertTrue(record["success"])
        self.assertGreater(record["execution_time"], 0.0)
        self.assertEqual(record["returned_data"], "Hello, Nova User")
        self.assertIsNone(record["error_message"])
        self.assertGreater(record["timestamp"], 0.0)

    def test_failure_action_recording(self):
        params = {"reason": "DBTimeout"}
        
        # Verify action still throws exception
        with self.assertRaises(ValueError) as ctx:
            self.failure_action.execute(params)
        self.assertEqual(str(ctx.exception), "Failed operation: DBTimeout")

        # Verify action was recorded as failure in working memory
        recent = self.wm.get("recent_actions")
        self.assertEqual(len(recent), 1)
        record = recent[0]

        self.assertEqual(record["action_name"], "dummy_failure")
        self.assertEqual(record["parameters"], params)
        self.assertIsNone(record["result"])
        self.assertFalse(record["success"])
        self.assertGreater(record["execution_time"], 0.0)
        self.assertIsNone(record["returned_data"])
        self.assertEqual(record["error_message"], "Failed operation: DBTimeout")

    def test_explicit_working_memory_injection(self):
        # Create a second working memory instance
        another_wm = WorkingMemory()
        
        # Explicitly inject the second working memory to success_action
        self.success_action.working_memory = another_wm
        
        # Run action
        self.success_action.execute({"name": "Explicit"})

        # Check that it recorded to another_wm and not self.wm
        self.assertEqual(len(another_wm.get("recent_actions")), 1)
        self.assertEqual(len(self.wm.get("recent_actions")), 0)
        
        record = another_wm.get("recent_actions")[0]
        self.assertEqual(record["returned_data"], "Hello, Explicit")

if __name__ == "__main__":
    unittest.main()
