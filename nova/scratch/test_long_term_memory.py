import unittest
from unittest.mock import MagicMock, patch
import time
import os
import tempfile
import sqlite3

from nova.long_term_memory import Memory, SQLiteMemoryStorage, LongTermMemoryManager

class TestLongTermMemory(unittest.TestCase):
    def setUp(self):
        # Initialize an in-memory SQLite storage for unit testing
        self.storage = SQLiteMemoryStorage(db_path=":memory:")
        self.manager = LongTermMemoryManager(self.storage)

    def tearDown(self):
        self.storage.close()

    def test_memory_creation_and_fields(self):
        mem = self.manager.create_memory(
            category="facts",
            title="user birthday",
            content="June 12",
            importance=4,
            confidence=0.9,
            source="user_chat",
            tags=["personal", "birthday"],
            meta_notes="needs verification"
        )

        self.assertIsNotNone(mem.id)
        self.assertEqual(mem.category, "facts")
        self.assertEqual(mem.title, "user birthday")
        self.assertEqual(mem.content, "June 12")
        self.assertEqual(mem.importance, 4)
        self.assertEqual(mem.confidence, 0.9)
        self.assertEqual(mem.source, "user_chat")
        self.assertEqual(mem.tags, ["personal", "birthday"])
        self.assertEqual(mem.meta_notes, "needs verification")
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
        new_storage.close()

    def test_working_memory_independence(self):
        # Verify that working_memory module is not imported in long_term_memory
        import sys
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

    def test_schema_migrations_and_indexes(self):
        fd, path = tempfile.mkstemp()
        try:
            # 1. Initialize a connection manually at version 1
            conn = sqlite3.connect(path)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS schema_info (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS long_term_memories (
                    id TEXT PRIMARY KEY,
                    category TEXT NOT NULL,
                    title TEXT NOT NULL,
                    content TEXT NOT NULL,
                    importance INTEGER NOT NULL,
                    confidence REAL NOT NULL,
                    source TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    accessed_at REAL NOT NULL,
                    access_count INTEGER NOT NULL,
                    version INTEGER NOT NULL,
                    active INTEGER NOT NULL
                )
            """)
            conn.execute("INSERT INTO schema_info (version, applied_at) VALUES (1, ?)", (time.time(),))
            conn.commit()
            conn.close()

            # 2. Open via SQLiteMemoryStorage (which runs upgrades 2 and 3)
            storage = SQLiteMemoryStorage(db_path=path)
            
            # Verify columns (should contain meta_notes)
            cursor = storage.conn.cursor()
            cursor.execute("PRAGMA table_info(long_term_memories)")
            columns = [col[1] for col in cursor.fetchall()]
            self.assertIn("meta_notes", columns)

            # Verify indexes exist
            cursor.execute("SELECT name FROM sqlite_master WHERE type='index'")
            indexes = [idx[0] for idx in cursor.fetchall()]
            self.assertIn("idx_memories_category", indexes)
            self.assertIn("idx_memories_active", indexes)

            storage.close()
        finally:
            os.close(fd)
            os.remove(path)

    @patch("sqlite3.connect")
    def test_transaction_rollback_on_failure(self, mock_connect):
        # Create mock connection and cursor
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [("id", "TEXT"), ("category", "TEXT"), ("title", "TEXT"), ("content", "TEXT"), ("importance", "INTEGER"), ("confidence", "REAL"), ("source", "TEXT"), ("tags", "TEXT"), ("created_at", "REAL"), ("updated_at", "REAL"), ("accessed_at", "REAL"), ("access_count", "INTEGER"), ("version", "INTEGER"), ("active", "INTEGER"), ("meta_notes", "TEXT")]
        mock_conn.cursor.return_value = mock_cursor
        
        # When attempting to save, cursor execute raises IntegrityError
        def execute_side_effect(sql, *args, **kwargs):
            if "INSERT OR REPLACE" in sql:
                raise sqlite3.IntegrityError("Simulated DB lock")
            return MagicMock()
            
        mock_conn.execute.side_effect = execute_side_effect
        mock_connect.return_value = mock_conn

        # Instantiate fresh storage and manager
        storage = SQLiteMemoryStorage(db_path=":memory:")
        manager = LongTermMemoryManager(storage)
        
        with self.assertRaises(sqlite3.IntegrityError):
            manager.create_memory("facts", "title", "content")
        
        # Verify rollback is invoked
        mock_conn.rollback.assert_called_once()
        storage.close()

    def test_index_usage_chronology_and_category(self):
        self.manager.create_memory("facts", "fact 1", "val")
        
        # Run explain query plan
        cursor = self.storage.conn.cursor()
        cursor.execute("EXPLAIN QUERY PLAN SELECT * FROM long_term_memories WHERE category = 'facts'")
        plan = cursor.fetchall()
        
        plan_str = " ".join([p[3] for p in plan])
        self.assertIn("idx_memories_category", plan_str)

if __name__ == "__main__":
    unittest.main()
