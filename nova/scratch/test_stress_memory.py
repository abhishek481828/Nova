import unittest
import threading
import time
import random
from typing import Dict, Any

from nova.working_memory import WorkingMemory, SessionState, Interaction
from nova.actions.base import BaseAction
from nova.logger import logger

# Test Action
class StressTestAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "stress_action"

    def execute(self, params: Dict[str, Any]) -> str:
        return f"processed: {params.get('id')}"

class TestStressMemory(unittest.TestCase):
    def setUp(self):
        self.wm = WorkingMemory()
        self.iterations = 200
        self.exception_caught = False
        self.error_messages = []

    def tearDown(self):
        BaseAction._shared_working_memory = None

    def test_concurrent_stress(self):
        threads = []

        # 1. Voice Loop Updates Worker
        def voice_worker():
            try:
                states = ["active", "idle", "inactive"]
                for i in range(self.iterations):
                    self.wm.set("voice_session_state", random.choice(states))
                    self.wm.set("listening_state", random.choice(["idle", "listening"]))
                    self.wm.set("recognition_confidence", random.random())
                    self.wm.set("current_speaker", f"speaker_{i}")
                    time.sleep(0.001)
            except Exception as e:
                self.exception_caught = True
                self.error_messages.append(f"Voice worker failed: {e}")

        # 2. Browser Event Updates Worker
        def browser_worker():
            try:
                for i in range(self.iterations):
                    self.wm.set("open_tabs_count", random.randint(1, 10))
                    self.wm.set("current_url", f"https://site-{i}.com")
                    self.wm.set("tab_title", f"Title {i}")
                    
                    history = list(self.wm.get("navigation_history") or [])
                    history.append(f"https://history-{i}.com")
                    self.wm.set("navigation_history", history)
                    time.sleep(0.001)
            except Exception as e:
                self.exception_caught = True
                self.error_messages.append(f"Browser worker failed: {e}")

        # 3. Action Execution Worker
        def action_worker():
            try:
                action = StressTestAction()
                for i in range(self.iterations):
                    action.execute({"id": i})
                    time.sleep(0.001)
            except Exception as e:
                self.exception_caught = True
                self.error_messages.append(f"Action worker failed: {e}")

        # 4. Context Manager Worker
        def context_worker():
            try:
                for i in range(self.iterations):
                    ctx_name = f"context_{i}"
                    # Temporary context block
                    with self.wm.context_manager.temporary(ctx_name, {"index": i}):
                        current = self.wm.context_manager.current_context
                        self.assertEqual(current.name, ctx_name)
                    time.sleep(0.001)
            except Exception as e:
                self.exception_caught = True
                self.error_messages.append(f"Context worker failed: {e}")

        # 5. Snapshot & Restore Worker
        def snapshot_worker():
            try:
                for i in range(self.iterations):
                    snap = self.wm.snapshot()
                    # Make some edits
                    self.wm.set("current_task", f"Task {i}")
                    # Restore snapshot
                    self.wm.restore(snap)
                    time.sleep(0.002)
            except Exception as e:
                self.exception_caught = True
                self.error_messages.append(f"Snapshot worker failed: {e}")

        # Spawn all worker threads
        t1 = threading.Thread(target=voice_worker)
        t2 = threading.Thread(target=browser_worker)
        t3 = threading.Thread(target=action_worker)
        t4 = threading.Thread(target=context_worker)
        t5 = threading.Thread(target=snapshot_worker)

        threads = [t1, t2, t3, t4, t5]

        # Start
        for t in threads:
            t.start()

        # Join
        for t in threads:
            t.join()

        # Assert no worker threw an exception
        self.assertFalse(self.exception_caught, f"Concurrency errors caught: {self.error_messages}")

        # Verify final state is readable
        self.assertIsNotNone(self.wm.snapshot())
        logger.info("Stress tests completed successfully under heavy concurrency.")

if __name__ == "__main__":
    unittest.main()
