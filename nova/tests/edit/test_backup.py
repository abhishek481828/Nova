"""
Tests for BackupManager.
"""
import tempfile
import unittest
from pathlib import Path
from nova.edit.backup import BackupManager, MAX_BACKUPS_PER_FILE

class TestBackupManager(unittest.TestCase):
    def test_backup_and_restore(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bm = BackupManager(root)
            
            rel_path = "src/main.py"
            file_path = root / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("print('hello')", encoding="utf-8")
            
            # Backup
            backup_path = bm.backup(rel_path)
            self.assertIsNotNone(backup_path)
            self.assertTrue(backup_path.exists())
            
            # Modify file
            file_path.write_text("print('hello world')", encoding="utf-8")
            
            # Restore content
            restored = bm.restore(rel_path)
            self.assertEqual(restored, "print('hello')")

    def test_backup_pruning(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bm = BackupManager(root)
            
            rel_path = "src/utils.py"
            file_path = root / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text("v1", encoding="utf-8")
            
            # Create MAX_BACKUPS_PER_FILE + 3 backups
            for i in range(MAX_BACKUPS_PER_FILE + 3):
                file_path.write_text(f"v{i}", encoding="utf-8")
                bm.backup(rel_path)
                
            backups = bm.list_backups(rel_path)
            # Should be capped at MAX_BACKUPS_PER_FILE
            self.assertEqual(len(backups), MAX_BACKUPS_PER_FILE)
            
    def test_backup_non_existent_file(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            bm = BackupManager(root)
            backup_path = bm.backup("non_existent.py")
            self.assertIsNone(backup_path)
            
            restored = bm.restore("non_existent.py")
            self.assertIsNone(restored)
