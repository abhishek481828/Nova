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
        mock_conn.cursor.return_value = mock_cursor
        
        # When attempting to save, cursor execute raises IntegrityError
        last_sql = [None]
        def execute_side_effect(sql, *args, **kwargs):
            last_sql[0] = sql
            if ("INSERT" in sql or "UPDATE" in sql) and "schema_info" not in sql:
                raise sqlite3.IntegrityError("Simulated DB lock")
            return MagicMock()
            
        mock_conn.execute.side_effect = execute_side_effect
        mock_cursor.execute.side_effect = execute_side_effect
        mock_cursor.fetchone.return_value = None

        def fetchall_side_effect():
            if last_sql[0] and "table_info" in last_sql[0]:
                return [
                    (0, "id", "TEXT", 1, None, 1),
                    (1, "category", "TEXT", 1, None, 0),
                    (2, "title", "TEXT", 1, None, 0),
                    (3, "content", "TEXT", 1, None, 0),
                    (4, "importance", "INTEGER", 1, None, 0),
                    (5, "confidence", "REAL", 1, None, 0),
                    (6, "source", "TEXT", 1, None, 0),
                    (7, "tags", "TEXT", 1, None, 0),
                    (8, "created_at", "REAL", 1, None, 0),
                    (9, "updated_at", "REAL", 1, None, 0),
                    (10, "accessed_at", "REAL", 1, None, 0),
                    (11, "access_count", "INTEGER", 1, None, 0),
                    (12, "version", "INTEGER", 1, None, 0),
                    (13, "active", "INTEGER", 1, None, 0),
                    (14, "meta_notes", "TEXT", 0, "''", 0)
                ]
            return []
        mock_cursor.fetchall.side_effect = fetchall_side_effect
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

    def test_memory_classification_validation(self):
        # Create memory with unregistered category raises ValueError
        with self.assertRaises(ValueError):
            self.manager.create_memory(category="custom_test_cat", title="T", content="C")

        # Register custom category on classifier
        self.manager.classifier.register_category("custom_test_cat")
        
        # Now it succeeds
        mem = self.manager.create_memory(category="custom_test_cat", title="T", content="C")
        self.assertEqual(mem.category, "custom_test_cat")

        # Attempting to update to an unregistered category raises ValueError
        with self.assertRaises(ValueError):
            self.manager.update_memory(mem.id, category="another_fake_cat")

    def test_heuristic_text_classification(self):
        classifier = self.manager.classifier
        
        # Test heuristic matching paths
        self.assertEqual(classifier.classify_text("My name is Abhishek"), "user_profile")
        self.assertEqual(classifier.classify_text("I live in San Francisco"), "user_profile")
        
        self.assertEqual(classifier.classify_text("I prefer dark mode"), "preferences")
        self.assertEqual(classifier.classify_text("My favorite food is pizza"), "preferences")
        
        self.assertEqual(classifier.classify_text("Developing a new Python repository"), "projects")
        self.assertEqual(classifier.classify_text("I bought a new computer"), "devices")
        
        self.assertEqual(classifier.classify_text("I want to run a marathon next year"), "goals")
        self.assertEqual(classifier.classify_text("Fluent in Javascript coding"), "skills")
        
        self.assertEqual(classifier.classify_text("Alice is my sister"), "relationships")
        self.assertEqual(classifier.classify_text("Did you know that water boils at 100C?"), "facts")
        
        self.assertEqual(classifier.classify_text("Generic sentence that falls back"), "knowledge")

    def test_retrieval_structural_filters(self):
        m1 = self.manager.create_memory("facts", "Abhishek Profile Birthday", "June 12", importance=4, tags=["personal", "date"])
        m2 = self.manager.create_memory("preferences", "Abhishek preference food", "pizza is great", importance=2, tags=["food"])
        m3 = self.manager.create_memory("goals", "Run Marathon", "want to complete marathon", importance=5, tags=["health", "personal"])
        
        # 1. Search by category
        res = self.manager.retriever.retrieve(category="preferences")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].id, m2.id)
        
        # 2. Search by tag
        res = self.manager.retriever.retrieve(tags=["personal"])
        self.assertEqual(len(res), 2)
        
        # 3. Search by keywords
        res = self.manager.retriever.retrieve(keywords=["Marathon"])
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].id, m3.id)
        
        # 4. Search by title
        res = self.manager.retriever.retrieve(title="Profile")
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].id, m1.id)
        
        # 5. Search by metadata
        res = self.manager.retriever.retrieve(metadata={"importance": 5})
        self.assertEqual(len(res), 1)
        self.assertEqual(res[0].id, m3.id)

    def test_retrieval_semantic_delegation(self):
        from nova.long_term_memory import BaseSemanticRetriever
        
        m1 = Memory(id="sem-1", category="goals", title="Aim high", content="Climb Mt Everest", importance=5, tags=["climbing"])
        m2 = Memory(id="sem-2", category="facts", title="Trivia facts", content="Everest is tall", importance=3, tags=["climbing"])
        
        mock_backend = MagicMock(spec=BaseSemanticRetriever)
        mock_backend.retrieve_semantic.return_value = [m1, m2]
        
        # Inject semantic backend
        self.manager.retriever.semantic_backend = mock_backend
        
        # 1. Verify semantic search is called
        res = self.manager.retriever.retrieve(query="Everest info")
        mock_backend.retrieve_semantic.assert_called_once_with("Everest info")
        self.assertEqual(len(res), 2)
        
        # 2. Verify post-retrieval structural filters (e.g. category facts filter on semantic yields)
        res_facts = self.manager.retriever.retrieve(query="Everest info", category="facts")
        self.assertEqual(len(res_facts), 1)
        self.assertEqual(res_facts[0].id, m2.id)

    def test_relevance_ranking_sort_order(self):
        # Create 3 memories with distinct parameters
        m_low = self.manager.create_memory("knowledge", "low rank", "content", importance=1, confidence=0.5)
        m_med = self.manager.create_memory("facts", "medium rank", "content", importance=3, confidence=0.8)
        m_high = self.manager.create_memory("user_profile", "high rank", "content", importance=5, confidence=1.0)
        
        # Verify retrieve sorts descending by score
        res = self.manager.retriever.retrieve()
        self.assertEqual(res[0].id, m_high.id)
        self.assertEqual(res[1].id, m_med.id)
        self.assertEqual(res[2].id, m_low.id)

    def test_ranking_time_decay(self):
        # Create fresh memory
        m_fresh = self.manager.create_memory("facts", "fresh fact", "content", importance=4)
        
        # Create old memory (decayed by 2 days)
        m_old = self.manager.create_memory("facts", "old fact", "content", importance=4)
        m_old.updated_at = time.time() - (86400 * 2)
        self.storage.save(m_old)
        
        res = self.manager.retriever.retrieve(category="facts")
        self.assertEqual(res[0].id, m_fresh.id)
        self.assertEqual(res[1].id, m_old.id)

    def test_custom_ranker_override(self):
        from nova.long_term_memory import BaseMemoryRanker
        
        class ReverseRanker(BaseMemoryRanker):
            def rank(self, memories):
                # Reverse list sorting
                return list(reversed(memories))
                
        # Inject custom ranker
        self.manager.retriever.ranker = ReverseRanker()
        
        m1 = self.manager.create_memory("facts", "fact A", "content")
        m2 = self.manager.create_memory("facts", "fact B", "content")
        
        # Standard query returns reverse ordered list
        res = self.manager.retriever.retrieve(category="facts")
        self.assertEqual(res[0].id, m2.id)
        self.assertEqual(res[1].id, m1.id)

    def test_duplicate_detection_and_merge(self):
        m1 = self.manager.create_memory("facts", "duplicate test", "first content", importance=2, tags=["first"])
        
        # Creating a duplicate in the same category/title should merge into m1
        m2 = self.manager.create_memory("facts", "duplicate test", "second content", importance=4, tags=["second"])
        
        self.assertEqual(m1.id, m2.id)
        self.assertEqual(m2.version, 2)
        self.assertEqual(m2.content, "second content")
        self.assertEqual(m2.importance, 4)
        self.assertEqual(sorted(m2.tags), ["first", "second"])

        # Listing memories should only show a single record
        memories = self.manager.list_memories(category="facts")
        self.assertEqual(len(memories), 1)

    def test_version_history_archiving(self):
        m = self.manager.create_memory("facts", "history test", "version 1", importance=2)
        m_id = m.id
        
        # Perform updates to increment version
        self.manager.update_memory(m_id, content="version 2")
        self.manager.update_memory(m_id, content="version 3")
        
        # Verify history versions exist in storage
        h1 = self.storage.get_history_version(m_id, 1)
        h2 = self.storage.get_history_version(m_id, 2)
        
        self.assertIsNotNone(h1)
        self.assertEqual(h1.content, "version 1")
        self.assertIsNotNone(h2)
        self.assertEqual(h2.content, "version 2")

    def test_rollback_historical_state(self):
        m = self.manager.create_memory("facts", "rollback test", "state 1", importance=2)
        m_id = m.id
        orig_created_at = m.created_at
        
        self.manager.update_memory(m_id, content="state 2")
        self.manager.update_memory(m_id, content="state 3")
        
        # Roll back to version 1
        rolled = self.manager.rollback_memory(m_id, 1)
        
        self.assertEqual(rolled.content, "state 1")
        self.assertEqual(rolled.version, 4)  # 1 (create) -> 2 (update) -> 3 (update) -> 4 (rollback)
        self.assertEqual(rolled.created_at, orig_created_at)  # Original timestamp preserved

    def test_consolidation_metadata_compression(self):
        from nova.long_term_memory import MemoryConsolidator
        m = Memory(
            category="facts",
            title="   Test Title  ",
            content="   Test Content.  ",
            tags=["tag", "TAG", "tag", "   another tag   "]
        )
        self.storage.save(m)
        
        consolidator = MemoryConsolidator(self.manager)
        compressed = consolidator.compress_all_metadata()
        
        self.assertEqual(compressed, 1)
        
        cleaned = self.storage.load(m.id)
        self.assertEqual(cleaned.title, "Test Title")
        self.assertEqual(cleaned.content, "Test Content.")
        self.assertEqual(cleaned.tags, ["another tag", "tag"])

    def test_consolidation_merge_duplicates(self):
        from nova.long_term_memory import MemoryConsolidator
        
        m1 = self.manager.create_memory("facts", "overlap topic", "This is some test content regarding python programming.", tags=["a"])
        # Wait a tiny bit to have different timestamps
        time.sleep(0.01)
        m2 = self.manager.create_memory("facts", "different overlaps", "This is some test content regarding python coding guidelines.", tags=["b"])
        
        consolidator = MemoryConsolidator(self.manager)
        proposals = consolidator.prepare_consolidation()
        
        # Verify proposal lists merge
        merge_proposals = [p for p in proposals if p.action == "merge"]
        self.assertEqual(len(merge_proposals), 1)
        
        prop = merge_proposals[0]
        self.assertEqual(prop.primary_id, m1.id)
        self.assertEqual(prop.target_ids, [m2.id])
        
        # Apply merge
        applied = consolidator.apply_consolidation(proposals)
        self.assertEqual(applied, 1)
        
        # Verify primary updated and target deactivated
        primary_loaded = self.storage.load(m1.id)
        target_loaded = self.storage.load(m2.id)
        
        self.assertIn("python coding guidelines", primary_loaded.content)
        self.assertEqual(primary_loaded.tags, ["a", "b"])
        self.assertFalse(target_loaded.active)

    def test_consolidation_obsolete_purge(self):
        from nova.long_term_memory import MemoryConsolidator
        
        # Older preference
        m_old = self.manager.create_memory("preferences", "user favorite editor", "User favorite editor is Emacs.")
        m_old.updated_at = time.time() - 100
        self.storage.save(m_old)
        
        # Newer preference
        m_new = self.manager.create_memory("preferences", "my favorite editor", "User favorite editor is VS Code.")
        
        consolidator = MemoryConsolidator(self.manager)
        proposals = consolidator.prepare_consolidation()
        
        obsolete_proposals = [p for p in proposals if p.action == "delete_obsolete"]
        self.assertEqual(len(obsolete_proposals), 1)
        
        prop = obsolete_proposals[0]
        self.assertEqual(prop.primary_id, m_new.id)
        self.assertEqual(prop.target_ids, [m_old.id])
        
        # Apply obsolete delete
        applied = consolidator.apply_consolidation(proposals)
        self.assertEqual(applied, 1)
        
        # Verify m_old is deleted
        self.assertIsNone(self.storage.load(m_old.id))
        
        # Now verify importance=5 exemption
        m_old_imp = self.manager.create_memory("preferences", "user favorite editor", "Important Emacs.", importance=5)
        m_old_imp.updated_at = time.time() - 100
        self.storage.save(m_old_imp)
        
        proposals_new = consolidator.prepare_consolidation()
        obsolete_proposals_new = [p for p in proposals_new if p.action == "delete_obsolete"]
        self.assertEqual(len(obsolete_proposals_new), 0)  # Exempted!

    def test_consolidation_inactive_archival(self):
        from nova.long_term_memory import MemoryConsolidator
        
        m_stale = self.manager.create_memory("knowledge", "stale fact", "Some content")
        m_stale.created_at = time.time() - 5000000  # Older than 30 days
        m_stale.updated_at = time.time() - 5000000
        self.storage.save(m_stale)
        
        consolidator = MemoryConsolidator(self.manager, inactive_seconds=2592000)
        proposals = consolidator.prepare_consolidation()
        
        archive_proposals = [p for p in proposals if p.action == "archive"]
        self.assertEqual(len(archive_proposals), 1)
        
        # Apply archival
        applied = consolidator.apply_consolidation(proposals)
        self.assertEqual(applied, 1)
        
        # Verify archived (inactive)
        stale_loaded = self.storage.load(m_stale.id)
        self.assertFalse(stale_loaded.active)

if __name__ == "__main__":
    unittest.main()
