import unittest
import time
import os
import tempfile

from nova.long_term_memory import Memory, SQLiteMemoryStorage, LongTermMemoryManager

class TestLongTermMemory(unittest.TestCase):
    def setUp(self):
        # Initialize an in-memory SQLite storage for unit testing
        self.storage = SQLiteMemoryStorage(db_path=":memory:")
        self.manager = LongTermMemoryManager(self.storage)

    def test_memory_creation_and_fields(self):
        mem = self.manager.create_memory(
            category="facts",
            title="user birthday",
            content="June 12",
            importance=4,
            confidence=0.9,
            source="user_chat",
            tags=["personal", "birthday"]
        )

        self.assertIsNotNone(mem.id)
        self.assertEqual(mem.category, "facts")
        self.assertEqual(mem.title, "user birthday")
        self.assertEqual(mem.content, "June 12")
        self.assertEqual(mem.importance, 4)
        self.assertEqual(mem.confidence, 0.9)
        self.assertEqual(mem.source, "user_chat")
        self.assertEqual(mem.tags, ["personal", "birthday"])
        self.assertEqual(mem.access_count, 0)
        self.assertEqual(mem.version, 1)
        self.assertTrue(mem.active)

    def test_validation_constraints(self):
        # Empty title raises ValueError
        with self.assertRaises(ValueError):
            Memory(title="", content="some facts")

        # Invalid importance score raises ValueError
        with self.assertRaises(ValueError):
            self.manager.create_memory("facts", "test", "val", importance=6)

        with self.assertRaises(ValueError):
            self.manager.create_memory("facts", "test", "val", importance=0)

        # Invalid confidence score raises ValueError
        with self.assertRaises(ValueError):
            self.manager.create_memory("facts", "test", "val", confidence=-0.1)

        # Invalid type content raises TypeError
        with self.assertRaises(TypeError):
            Memory(title="test", content=123)

    def test_get_memory_updates_tracking(self):
        mem = self.manager.create_memory("facts", "title", "content")
        
        # Access memory via manager
        accessed1 = self.manager.get_memory(mem.id)
        self.assertEqual(accessed1.access_count, 1)
        self.assertGreater(accessed1.accessed_at, 0)
        
        # Access memory again
        accessed2 = self.manager.get_memory(mem.id)
        self.assertEqual(accessed2.access_count, 2)

    def test_update_memory_increments_version(self):
        mem = self.manager.create_memory("facts", "original title", "content")
        self.assertEqual(mem.version, 1)

        updated = self.manager.update_memory(
            mem.id,
            title="new title",
            importance=5,
            tags=["updated"]
        )

        self.assertEqual(updated.title, "new title")
        self.assertEqual(updated.importance, 5)
        self.assertEqual(updated.tags, ["updated"])
        self.assertEqual(updated.version, 2)
        self.assertGreater(updated.updated_at, mem.created_at)

    def test_delete_memory(self):
        mem = self.manager.create_memory("facts", "to delete", "content")
        self.assertIsNotNone(self.manager.get_memory(mem.id))

        deleted = self.manager.delete_memory(mem.id)
        self.assertTrue(deleted)
        self.assertIsNone(self.manager.get_memory(mem.id))

    def test_list_memories_filtering(self):
        self.manager.create_memory("facts", "fact 1", "content")
        self.manager.create_memory("preferences", "pref 1", "content")
        inactive_mem = self.manager.create_memory("facts", "fact 2", "content")
        self.manager.update_memory(inactive_mem.id, active=False)

        # List active facts
        facts = self.manager.list_memories(category="facts", active_only=True)
        self.assertEqual(len(facts), 1)
        self.assertEqual(facts[0].title, "fact 1")

        # List all preferences
        prefs = self.manager.list_memories(category="preferences")
        self.assertEqual(len(prefs), 1)

        # List inactive memories too
        all_facts = self.manager.list_memories(category="facts", active_only=False)
        self.assertEqual(len(all_facts), 2)

    def test_import_and_export_memories(self):
        self.manager.create_memory("facts", "fact 1", "val 1", tags=["tag1"])
        self.manager.create_memory("facts", "fact 2", "val 2", tags=["tag2"])

        # Export
        exported = self.manager.export_memories()
        self.assertEqual(len(exported), 2)
        self.assertEqual(exported[0]["title"], "fact 1")
        self.assertEqual(exported[0]["tags"], ["tag1"])

        # Import into a fresh manager
        new_storage = SQLiteMemoryStorage(db_path=":memory:")
        new_manager = LongTermMemoryManager(new_storage)
        
        imported_count = new_manager.import_memories(exported)
        self.assertEqual(imported_count, 2)
        
        imported_list = new_manager.list_memories()
        self.assertEqual(len(imported_list), 2)
        self.assertEqual(imported_list[1].title, "fact 2")

    def test_working_memory_independence(self):
        # Verify that working_memory module is not imported in long_term_memory
        import sys
        # Clear modules dictionary to ensure clean search
        if "nova.working_memory" in sys.modules:
            orig_wm = sys.modules["nova.working_memory"]
            del sys.modules["nova.working_memory"]
        else:
            orig_wm = None

        try:
            import nova.long_term_memory
            self.assertNotIn("nova.working_memory", sys.modules, "Long-term memory module must not import Working Memory.")
        finally:
            if orig_wm:
                sys.modules["nova.working_memory"] = orig_wm

if __name__ == "__main__":
    unittest.main()
