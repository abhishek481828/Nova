"""Integration tests for CodeIntelligenceEngine"""
import json
import tempfile
import time
import unittest
from pathlib import Path

from nova.code.engine import CodeIntelligenceEngine
from nova.code.context import CodeContext
from nova.code.parser.base import SymbolKind


def _reset_cie():
    CodeIntelligenceEngine._instance = None


def _scaffold_python_project(root: Path) -> None:
    (root / ".git").mkdir()
    (root / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    (root / "pyproject.toml").write_text('[project]\nname = "testapp"\n')
    src = root / "src"
    src.mkdir()
    (src / "models.py").write_text(
        "from sqlalchemy import Base\n\n"
        "class User(Base):\n"
        '    """User model."""\n'
        "    id: int\n"
        "    name: str\n"
    )
    (src / "routes.py").write_text(
        "from flask import Flask\napp = Flask(__name__)\n\n"
        "@app.route('/users', methods=['GET'])\n"
        "def list_users():\n    pass\n\n"
        "@app.route('/users', methods=['POST'])\n"
        "def create_user():\n    pass\n"
    )
    (src / "services.py").write_text(
        "def authenticate(user, password):\n"
        "    return validate(user)\n\n"
        "def validate(user):\n"
        "    return True\n"
    )


def _scaffold_ts_project(root: Path) -> None:
    (root / "package.json").write_text(json.dumps({"name": "myapp", "dependencies": {"react": "^18"}}))
    (root / "index.tsx").write_text(
        "import React from 'react';\n"
        "const App = () => <div>Hello</div>;\n"
        "export default App;\n"
    )
    (root / "hooks.ts").write_text(
        "const useAuth = () => { return {}; };\n"
        "const useTheme = () => { return {}; };\n"
    )
    (root / "server.ts").write_text(
        "import express from 'express';\n"
        "const router = express.Router();\n"
        "router.get('/users', getUsers);\n"
        "router.post('/users', createUser);\n"
    )


class TestCIEPythonProject(unittest.TestCase):
    def setUp(self):
        _reset_cie()
        from nova.project.engine import ProjectAwarenessEngine
        ProjectAwarenessEngine._instance = None

    def _index_dir(self, root: Path) -> CodeContext:
        """Run full index synchronously on a temp project."""
        from nova.project.engine import ProjectAwarenessEngine
        pae = ProjectAwarenessEngine()
        project_ctx = pae.scan(root)

        engine = CodeIntelligenceEngine()
        engine._full_index(project_ctx)
        return engine.get_context()

    def test_detects_flask_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold_python_project(root)
            ctx = self._index_dir(root)
        routes = ctx.find_routes()
        self.assertGreaterEqual(len(routes), 2)

    def test_detects_sqlalchemy_models(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold_python_project(root)
            ctx = self._index_dir(root)
        models = ctx.find_models()
        names = [m.name for m in models]
        self.assertIn("User", names)

    def test_find_symbol_by_name(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold_python_project(root)
            ctx = self._index_dir(root)
        hits = ctx.find_symbol("list_users")
        self.assertTrue(len(hits) > 0)

    def test_call_graph_built(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold_python_project(root)
            ctx = self._index_dir(root)
        callers = ctx.find_callers("validate")
        # authenticate calls validate
        caller_names = [e.caller_name for e in callers]
        self.assertTrue(any("authenticate" in n for n in caller_names))

    def test_stats_populated(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold_python_project(root)
            ctx = self._index_dir(root)
        s = ctx.stats()
        self.assertGreater(s["total_symbols"], 0)
        self.assertGreater(s["total_files"], 0)


class TestCIETypeScriptProject(unittest.TestCase):
    def setUp(self):
        _reset_cie()
        from nova.project.engine import ProjectAwarenessEngine
        ProjectAwarenessEngine._instance = None

    def _index_dir(self, root: Path) -> CodeContext:
        from nova.project.engine import ProjectAwarenessEngine
        pae = ProjectAwarenessEngine()
        project_ctx = pae.scan(root)
        engine = CodeIntelligenceEngine()
        engine._full_index(project_ctx)
        return engine.get_context()

    def test_react_components_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold_ts_project(root)
            ctx = self._index_dir(root)
        comps = ctx.find_components()
        self.assertGreater(len(comps), 0)

    def test_hooks_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold_ts_project(root)
            ctx = self._index_dir(root)
        hooks = ctx.find_hooks()
        names = [h.name for h in hooks]
        self.assertIn("useAuth", names)
        self.assertIn("useTheme", names)

    def test_express_routes_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold_ts_project(root)
            ctx = self._index_dir(root)
        routes = ctx.find_routes()
        self.assertGreaterEqual(len(routes), 2)


class TestCIEIncrementalUpdate(unittest.TestCase):
    def setUp(self):
        _reset_cie()
        from nova.project.engine import ProjectAwarenessEngine
        ProjectAwarenessEngine._instance = None

    def test_file_added_incrementally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold_python_project(root)
            from nova.project.engine import ProjectAwarenessEngine
            pae = ProjectAwarenessEngine()
            project_ctx = pae.scan(root)
            engine = CodeIntelligenceEngine()
            engine._full_index(project_ctx)

            # Add a new file
            new_file = root / "src" / "new_service.py"
            new_file.write_text("def send_email(to):\n    pass\n")

            engine.on_file_change("added", "src/new_service.py", root)
            ctx = engine.get_context()

        hits = ctx.find_symbol("send_email")
        self.assertGreater(len(hits), 0)

    def test_file_deleted_incrementally(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _scaffold_python_project(root)
            from nova.project.engine import ProjectAwarenessEngine
            pae = ProjectAwarenessEngine()
            project_ctx = pae.scan(root)
            engine = CodeIntelligenceEngine()
            engine._full_index(project_ctx)
            ctx = engine.get_context()

            # Verify symbol exists
            self.assertTrue(len(ctx.find_symbol("list_users")) > 0)

            # Delete the file
            engine.on_file_change("deleted", "src/routes.py", root)

        hits = ctx.find_symbol("list_users")
        self.assertEqual(hits, [])


class TestCIESingleton(unittest.TestCase):
    def test_singleton_identity(self):
        _reset_cie()
        a = CodeIntelligenceEngine()
        b = CodeIntelligenceEngine()
        self.assertIs(a, b)

    def test_get_context_none_before_index(self):
        _reset_cie()
        engine = CodeIntelligenceEngine()
        self.assertIsNone(engine.get_context())
