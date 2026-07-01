import unittest
import time

from nova.core.memory import WorkingMemory, SessionState
from nova.core.context import MemoryContext

class TestContextMemory(unittest.TestCase):
    def setUp(self):
        self.wm = WorkingMemory()
        self.cm = self.wm.context_manager

    def test_initial_context_state(self):
        self.assertIsNone(self.cm.current_context)
        self.assertIsNone(self.cm.previous_context)
        self.assertEqual(len(self.wm.state.active_contexts), 0)

    def test_validation_constraints(self):
        # Verify valid inputs do not throw
        ctx = MemoryContext(name="valid")
        self.wm.set("active_contexts", [ctx])
        self.wm.set("previous_context", ctx)
        self.assertEqual(self.wm.get("previous_context"), ctx)

        # Verify invalid types raise exceptions
        with self.assertRaises(TypeError):
            self.wm.set("active_contexts", "not-a-list")
        
        with self.assertRaises(TypeError):
            self.wm.set("active_contexts", ["not-a-context"])

        with self.assertRaises(TypeError):
            self.wm.set("previous_context", "not-a-context")

    def test_enter_and_exit_context(self):
        # Enter context
        ctx1 = self.cm.enter_context("email_drafting", {"recipient": "boss@company.com"})
        
        self.assertEqual(self.cm.current_context, ctx1)
        self.assertEqual(len(self.wm.state.active_contexts), 1)
        self.assertEqual(self.cm.current_context.name, "email_drafting")
        self.assertEqual(self.cm.current_context.metadata["recipient"], "boss@company.com")
        self.assertGreater(self.cm.current_context.timestamp, 0.0)

        # Exit context
        popped = self.cm.exit_context("email_drafting")
        self.assertEqual(popped, ctx1)
        self.assertIsNone(self.cm.current_context)
        self.assertEqual(self.cm.previous_context, ctx1)

    def test_nested_contexts_lifo(self):
        ctx1 = self.cm.enter_context("parent_task")
        ctx2 = self.cm.enter_context("child_subtask", {"depth": 1})
        ctx3 = self.cm.enter_context("grandchild_query")

        self.assertEqual(self.cm.current_context, ctx3)
        self.assertEqual(len(self.wm.state.active_contexts), 3)

        # Pop grandchild
        popped3 = self.cm.exit_context()
        self.assertEqual(popped3, ctx3)
        self.assertEqual(self.cm.current_context, ctx2)
        self.assertEqual(self.cm.previous_context, ctx3)

        # Pop child
        popped2 = self.cm.exit_context()
        self.assertEqual(popped2, ctx2)
        self.assertEqual(self.cm.current_context, ctx1)
        self.assertEqual(self.cm.previous_context, ctx2)

    def test_switch_context(self):
        ctx1 = self.cm.enter_context("browsing")
        ctx2 = self.cm.switch_context("searching", {"query": "playwright"})

        self.assertEqual(self.cm.current_context, ctx2)
        self.assertEqual(self.cm.previous_context, ctx1)
        self.assertEqual(len(self.wm.state.active_contexts), 1)

    def test_temporary_context_manager(self):
        ctx_outer = self.cm.enter_context("outer")

        with self.cm.temporary("inner", {"key": "val"}) as ctx_inner:
            self.assertEqual(self.cm.current_context, ctx_inner)
            self.assertEqual(self.cm.current_context.name, "inner")
            self.assertEqual(len(self.wm.state.active_contexts), 2)

        # Exiting context block
        self.assertEqual(self.cm.current_context, ctx_outer)
        self.assertEqual(self.cm.previous_context.name, "inner")
        self.assertEqual(len(self.wm.state.active_contexts), 1)

    def test_temporary_context_manager_exception_safety(self):
        ctx_outer = self.cm.enter_context("outer")

        try:
            with self.cm.temporary("inner_fail"):
                self.assertEqual(self.cm.current_context.name, "inner_fail")
                raise ValueError("Interrupted!")
        except ValueError:
            pass

        # Ensure context was exited despite exception
        self.assertEqual(self.cm.current_context, ctx_outer)
        self.assertEqual(self.cm.previous_context.name, "inner_fail")
        self.assertEqual(len(self.wm.state.active_contexts), 1)

    def test_clear_contexts(self):
        self.cm.enter_context("ctx1")
        self.cm.enter_context("ctx2")
        self.cm.exit_context()

        self.assertIsNotNone(self.cm.current_context)
        self.assertIsNotNone(self.cm.previous_context)

        self.cm.clear_contexts()
        self.assertIsNone(self.cm.current_context)
        self.assertIsNone(self.cm.previous_context)
        self.assertEqual(len(self.wm.state.active_contexts), 0)

    def test_restore_context(self):
        ctx1 = self.cm.enter_context("original")
        self.cm.exit_context()

        self.assertIsNone(self.cm.current_context)
        self.assertEqual(self.cm.previous_context, ctx1)

        restored = self.cm.restore_context()
        self.assertEqual(restored, ctx1)
        self.assertEqual(self.cm.current_context, ctx1)
        self.assertIsNone(self.cm.previous_context)

    def test_snapshot_and_restore(self):
        ctx1 = self.cm.enter_context("base_context")
        ctx2 = self.cm.enter_context("nested_context", {"index": 1})
        self.cm.exit_context() # pops ctx2, leaves ctx1 as current, ctx2 as previous

        # Snapshot
        snap = self.wm.snapshot()
        self.assertEqual(snap["active_contexts"][0]["name"], "base_context")
        self.assertEqual(snap["previous_context"]["name"], "nested_context")

        # Mutate
        self.wm.clear()
        self.assertIsNone(self.wm.context_manager.current_context)

        # Restore
        self.wm.restore(snap)
        self.assertEqual(self.wm.context_manager.current_context.name, "base_context")
        self.assertEqual(self.wm.context_manager.previous_context.name, "nested_context")
        self.assertIsInstance(self.wm.context_manager.current_context, MemoryContext)
        self.assertIsInstance(self.wm.context_manager.previous_context, MemoryContext)

if __name__ == "__main__":
    unittest.main()
