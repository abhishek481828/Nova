"""Integration tests for nova.project.engine + full pipeline."""
import json
import tempfile
import time
import unittest
from pathlib import Path

from nova.project.engine import ProjectAwarenessEngine
from nova.project.context import ProjectContext


def _make_python_project(root: Path) -> None:
    """Scaffold a minimal Python project tree for integration tests."""
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        '[project]\nname = "test-proj"\nversion = "0.1.0"\n'
        'dependencies = ["flask>=2.0", "requests"]\n',
        encoding="utf-8",
    )
    src = root / "src"
    src.mkdir()
    (src / "main.py").write_text("import flask\n", encoding="utf-8")
    (src / "utils.py").write_text("import os\nimport sys\n", encoding="utf-8")
    (root / "requirements.txt").write_text("flask>=2.0\nrequests==2.28\n", encoding="utf-8")


def _make_node_project(root: Path) -> None:
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/dev\n", encoding="utf-8")
    (root / "package.json").write_text(json.dumps({
        "name": "my-node-app",
        "dependencies": {"react": "^18.0", "next": "^14.0"},
        "devDependencies": {"typescript": "^5.0"},
    }), encoding="utf-8")
    (root / "next.config.js").write_text("module.exports={}", encoding="utf-8")
    (root / "index.ts").write_text("import React from 'react';\n", encoding="utf-8")
    (root / "app.tsx").write_text("export default function App(){}\n", encoding="utf-8")


class TestProjectAwarenessEngineReset:
    """Utility to reset singleton between tests."""
    def setUp(self):
        # Reset singleton state
        ProjectAwarenessEngine._instance = None


class TestEnginePythonProject(TestProjectAwarenessEngineReset, unittest.TestCase):
    def test_full_scan_python(self):
        ProjectAwarenessEngine._instance = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_python_project(root)
            engine = ProjectAwarenessEngine()
            ctx = engine.scan(root)

        self.assertIsInstance(ctx, ProjectContext)
        self.assertEqual(ctx.name, "test-proj")
        self.assertTrue(ctx.is_git_repo)
        self.assertEqual(ctx.git_branch, "main")
        self.assertGreater(ctx.total_files, 0)
        self.assertIn("Python", ctx.all_language_names)

    def test_flask_framework_detected(self):
        ProjectAwarenessEngine._instance = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_python_project(root)
            engine = ProjectAwarenessEngine()
            ctx = engine.scan(root)
        self.assertIn("Flask", ctx.frameworks)

    def test_scan_duration_recorded(self):
        ProjectAwarenessEngine._instance = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_python_project(root)
            engine = ProjectAwarenessEngine()
            ctx = engine.scan(root)
        self.assertGreater(ctx.scan_duration_s, 0)

    def test_primary_language_python(self):
        ProjectAwarenessEngine._instance = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_python_project(root)
            engine = ProjectAwarenessEngine()
            ctx = engine.scan(root)
        self.assertEqual(ctx.primary_language, "Python")


class TestEngineNodeProject(TestProjectAwarenessEngineReset, unittest.TestCase):
    def test_full_scan_node(self):
        ProjectAwarenessEngine._instance = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_node_project(root)
            engine = ProjectAwarenessEngine()
            ctx = engine.scan(root)

        self.assertEqual(ctx.name, "my-node-app")
        self.assertIn("Next.js", ctx.frameworks)
        self.assertIn("React", ctx.frameworks)
        self.assertEqual(ctx.git_branch, "dev")

    def test_typescript_detected(self):
        ProjectAwarenessEngine._instance = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_node_project(root)
            engine = ProjectAwarenessEngine()
            ctx = engine.scan(root)
        self.assertIn("TypeScript", ctx.all_language_names)


class TestEngineCaching(TestProjectAwarenessEngineReset, unittest.TestCase):
    def test_cache_hit_returns_context(self):
        ProjectAwarenessEngine._instance = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_python_project(root)
            engine = ProjectAwarenessEngine()
            ctx1 = engine.scan(root)

            # Reset engine but not disk cache
            ProjectAwarenessEngine._instance = None
            engine2 = ProjectAwarenessEngine()
            # Override cache path to temp dir
            from nova.project.cache import ProjectCache
            engine2._cache = ProjectCache(root / "test_cache.json")
            engine2._cache.save(ctx1)
            ctx2 = engine2._cache.load(root)

        self.assertIsNotNone(ctx2)
        self.assertEqual(ctx2.name, ctx1.name)

    def test_stale_cache_returns_none(self):
        from nova.project.cache import ProjectCache
        with tempfile.TemporaryDirectory() as tmp:
            cache_path = Path(tmp) / "cache.json"
            cache = ProjectCache(cache_path)
            # Manually write an old entry
            entry = {str(Path(tmp)): {"last_scanned": time.time() - 9999, "root": tmp,
                                       "name": "old", "languages": [], "frameworks": [],
                                       "dependencies": {}, "dev_dependencies": {},
                                       "is_git_repo": False, "git_branch": None,
                                       "git_remote": None, "scan_duration_s": 0,
                                       "total_files": 0, "total_size_bytes": 0,
                                       "metadata": {}}}
            cache_path.write_text(json.dumps(entry), encoding="utf-8")
            result = cache.load(Path(tmp), ttl=600)
        self.assertIsNone(result)


class TestProjectContextSummary(unittest.TestCase):
    def test_summary_str(self):
        ProjectAwarenessEngine._instance = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_python_project(root)
            engine = ProjectAwarenessEngine()
            ctx = engine.scan(root)
        summary = ctx.summary
        self.assertIn("test-proj", summary)
        self.assertIn("Python", summary)
        self.assertIn("git:main", summary)

    def test_to_dict_roundtrip(self):
        ProjectAwarenessEngine._instance = None
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _make_python_project(root)
            engine = ProjectAwarenessEngine()
            ctx = engine.scan(root)
        d = ctx.to_dict()
        restored = ProjectContext.from_dict(d)
        self.assertEqual(restored.name, ctx.name)
        self.assertEqual(restored.git_branch, ctx.git_branch)


class TestEngineSingleton(unittest.TestCase):
    def test_singleton_returns_same_instance(self):
        ProjectAwarenessEngine._instance = None
        a = ProjectAwarenessEngine()
        b = ProjectAwarenessEngine()
        self.assertIs(a, b)


class TestGetProjectContext(unittest.TestCase):
    def test_returns_none_before_scan(self):
        ProjectAwarenessEngine._instance = None
        from nova.project import get_project_context
        ctx = get_project_context()
        self.assertIsNone(ctx)
