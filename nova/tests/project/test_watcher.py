"""Tests for nova.project.watcher"""
import time
import tempfile
import threading
import unittest
from pathlib import Path

from nova.project.watcher import ProjectWatcher


class TestProjectWatcher(unittest.TestCase):
    def _make_watcher(self, root, events):
        def on_change(event_type, path_str):
            events.append((event_type, path_str))
        return ProjectWatcher(root=root, on_change=on_change, poll_interval=0.1)

    def test_detects_added_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            events = []
            w = self._make_watcher(root, events)
            w.start()
            time.sleep(0.15)
            (root / "new.py").write_text("x=1", encoding="utf-8")
            time.sleep(0.25)
            w.stop()
        added = [e for e in events if e[0] == "added"]
        self.assertTrue(any("new.py" in e[1] for e in added))

    def test_detects_deleted_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "del.py"
            f.write_text("x=1", encoding="utf-8")
            events = []
            w = self._make_watcher(root, events)
            w.start()
            time.sleep(0.15)
            f.unlink()
            time.sleep(0.25)
            w.stop()
        deleted = [e for e in events if e[0] == "deleted"]
        self.assertTrue(any("del.py" in e[1] for e in deleted))

    def test_detects_modified_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "mod.py"
            f.write_text("x=1", encoding="utf-8")
            events = []
            w = self._make_watcher(root, events)
            w.start()
            time.sleep(0.2)
            f.write_text("x=2", encoding="utf-8")
            # Touch mtime to ensure change is detected
            now = time.time()
            import os
            os.utime(f, (now + 1, now + 1))
            time.sleep(0.25)
            w.stop()
        modified = [e for e in events if e[0] == "modified"]
        self.assertTrue(any("mod.py" in e[1] for e in modified))

    def test_start_stop_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            w = self._make_watcher(root, [])
            w.start()
            self.assertTrue(w.is_running())
            w.stop()
            self.assertFalse(w.is_running())

    def test_double_start_safe(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            w = self._make_watcher(root, [])
            w.start()
            w.start()  # should not spawn second thread
            self.assertTrue(w.is_running())
            w.stop()

    def test_ignored_dirs_not_watched(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            node_modules = root / "node_modules"
            node_modules.mkdir()
            events = []
            w = self._make_watcher(root, events)
            w.start()
            time.sleep(0.15)
            (node_modules / "secret.js").write_text("x=1", encoding="utf-8")
            time.sleep(0.25)
            w.stop()
        # node_modules should be ignored; no event for its contents
        self.assertFalse(any("node_modules" in e[1] for e in events))
