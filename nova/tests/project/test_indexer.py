"""Tests for nova.project.indexer"""
import asyncio
import tempfile
import unittest
from pathlib import Path

from nova.project.indexer import (
    IGNORED_DIRS,
    build_index_sync,
    update_index_for_file,
)


class TestBuildIndexSync(unittest.TestCase):
    def test_indexes_python_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "main.py").write_text("import os\nimport sys\n", encoding="utf-8")
            (root / "utils.py").write_text("from pathlib import Path\n", encoding="utf-8")
            index = build_index_sync(root)
        self.assertIn("main.py", index)
        self.assertIn("utils.py", index)

    def test_extracts_python_imports(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "app.py").write_text(
                "import os\nimport sys\nfrom pathlib import Path\n", encoding="utf-8"
            )
            index = build_index_sync(root)
        node = index["app.py"]
        self.assertIn("os", node.imports)
        self.assertIn("sys", node.imports)
        self.assertIn("pathlib", node.imports)

    def test_ignored_dirs_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for ignored in ["node_modules", "__pycache__", ".venv", ".git"]:
                d = root / ignored
                d.mkdir()
                (d / "file.py").write_text("x=1", encoding="utf-8")
            (root / "main.py").write_text("x=1", encoding="utf-8")
            index = build_index_sync(root)
        keys = list(index.keys())
        self.assertEqual(keys, ["main.py"])

    def test_nested_dirs_indexed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            sub = root / "nova" / "core"
            sub.mkdir(parents=True)
            (sub / "memory.py").write_text("x=1", encoding="utf-8")
            index = build_index_sync(root)
        self.assertTrue(any("memory.py" in k for k in index.keys()))

    def test_large_file_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            big = root / "big.py"
            big.write_bytes(b"x" * (3 * 1024 * 1024))  # 3 MB
            index = build_index_sync(root)
        self.assertNotIn("big.py", index)

    def test_image_files_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "logo.png").write_bytes(b"\x89PNG")
            (root / "main.py").write_text("x=1", encoding="utf-8")
            index = build_index_sync(root)
        self.assertNotIn("logo.png", index)
        self.assertIn("main.py", index)

    def test_empty_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = build_index_sync(Path(tmp))
        self.assertEqual(index, {})

    def test_file_node_fields_populated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            f = root / "hello.py"
            f.write_text("print('hello')", encoding="utf-8")
            index = build_index_sync(root)
        node = index["hello.py"]
        self.assertEqual(node.extension, ".py")
        self.assertGreater(node.size_bytes, 0)
        self.assertGreater(node.mtime, 0)


class TestUpdateIndexForFile(unittest.TestCase):
    def test_adds_new_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = {}
            f = root / "new.py"
            f.write_text("import json\n", encoding="utf-8")
            result = update_index_for_file(index, root, f)
        self.assertIn("new.py", result)

    def test_removes_deleted_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = {"gone.py": None}  # type: ignore
            result = update_index_for_file(index, root, root / "gone.py")
        self.assertNotIn("gone.py", result)

    def test_updates_modified_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            index = build_index_sync(root)
            f = root / "mod.py"
            f.write_text("import os\n", encoding="utf-8")
            update_index_for_file(index, root, f)
            f.write_text("import os\nimport sys\n", encoding="utf-8")
            update_index_for_file(index, root, f)
        node = index["mod.py"]
        self.assertIn("sys", node.imports)


class TestIgnoredDirsSet(unittest.TestCase):
    def test_contains_expected(self):
        for d in ["node_modules", ".git", "__pycache__", ".venv", "dist", "build"]:
            self.assertIn(d, IGNORED_DIRS)
