import unittest
import threading
import time
from pathlib import Path
import logging

from nova.core.memory import (
    WorkingMemory,
    get_working_memory,
    reset_working_memory,
)

class TestSharedWorkingMemory(unittest.TestCase):
    def setUp(self):
        # Guarantee a fresh shared memory instance before each test
        reset_working_memory()

    def test_singleton_returns_same_instance(self):
        wm1 = get_working_memory()
        wm2 = get_working_memory()
        self.assertIs(wm1, wm2)

    def test_reset_creates_new_instance(self):
        wm1 = get_working_memory()
        wm1.set("test_key", "test_value")
        
        # Reset should give a fresh one
        wm2 = reset_working_memory()
        self.assertIsNot(wm1, wm2)
        self.assertIsNone(wm2.get("test_key"))
        
        # get_working_memory should now return the fresh one
        wm3 = get_working_memory()
        self.assertIs(wm2, wm3)

    def test_shared_state_access(self):
        wm = get_working_memory()
        wm.set("shared_var", "hello")
        
        # Fetching it again via getter retrieves the same state
        self.assertEqual(get_working_memory().get("shared_var"), "hello")

    def test_thread_safety_same_instance(self):
        instances = []
        lock = threading.Lock()
        
        def worker():
            wm = get_working_memory()
            with lock:
                instances.append(wm)

        threads = [threading.Thread(target=worker) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads must retrieve the exact same WorkingMemory instance
        first_instance = instances[0]
        for inst in instances:
            self.assertIs(inst, first_instance)

    def test_thread_safety_concurrent_updates(self):
        wm = get_working_memory()
        errors = []

        def writer(thread_id):
            try:
                for idx in range(100):
                    wm.set(f"key_{thread_id}", idx)
                    time.sleep(0.0001)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"Thread execution threw errors: {errors}")
        for i in range(10):
            self.assertEqual(wm.get(f"key_{i}"), 99)

    def test_divergence_warning(self):
        # We want to verify that creating a second WorkingMemory instance triggers the logger warning,
        # but calling get_working_memory() does not.
        log_records = []
        class MockHandler(logging.Handler):
            def emit(self, record):
                log_records.append(record)

        import nova.core.memory as mem_mod
        logger = mem_mod.logger
        handler = MockHandler()
        logger.addHandler(handler)
        old_level = logger.level
        logger.setLevel(logging.WARNING)


        try:
            # First, fetch shared working memory. No warning should trigger.
            get_working_memory()
            self.assertEqual(len(log_records), 0)

            # Constructing a SECOND raw instance manually should trigger a warning.
            wm_raw = WorkingMemory()
            self.assertGreaterEqual(len(log_records), 1)
            warning_msg = log_records[-1].getMessage()
            self.assertIn("A new WorkingMemory instance is being created", warning_msg)
            self.assertIn("Use get_working_memory() in production", warning_msg)
        finally:
            logger.removeHandler(handler)
            logger.setLevel(old_level)

if __name__ == "__main__":
    unittest.main()
