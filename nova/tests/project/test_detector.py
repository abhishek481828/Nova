"""Tests for nova.project.detector"""
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open
import tempfile
import os

from nova.project.detector import (
    find_project_root,
    detect_languages,
    detect_frameworks,
    detect_git,
    detect_project_name,
)
from nova.project.context import LanguageInfo


class TestFindProjectRoot(unittest.TestCase):
    def test_finds_git_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            sub = root / "src" / "app"
            sub.mkdir(parents=True)
            result = find_project_root(sub)
            self.assertEqual(result, root)

    def test_finds_package_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "package.json").write_text("{}", encoding="utf-8")
            sub = root / "components"
            sub.mkdir()
            result = find_project_root(sub)
            self.assertEqual(result, root)

    def test_finds_pyproject_toml(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "pyproject.toml").write_text("[tool.poetry]", encoding="utf-8")
            result = find_project_root(root)
            self.assertEqual(result, root)

    def test_fallback_to_start(self):
        with tempfile.TemporaryDirectory() as tmp:
            deep = Path(tmp) / "a" / "b" / "c"
            deep.mkdir(parents=True)
            result = find_project_root(deep)
            self.assertEqual(result, deep.resolve())

    def test_stops_at_filesystem_root(self):
        # Should not raise even when walking past filesystem root
        result = find_project_root(Path("/"))
        self.assertIsInstance(result, Path)


class TestDetectLanguages(unittest.TestCase):
    def test_python_dominant(self):
        paths = ["main.py", "utils.py", "models.py", "README.md"]
        langs = detect_languages(paths)
        self.assertTrue(any(l.name == "Python" and l.primary for l in langs))

    def test_typescript_detected(self):
        paths = ["index.ts", "App.tsx", "server.ts", "client.ts"]
        langs = detect_languages(paths)
        names = [l.name for l in langs]
        self.assertIn("TypeScript", names)

    def test_mixed_project(self):
        paths = (
            ["file.py"] * 10
            + ["file.ts"] * 5
            + ["file.rs"] * 3
        )
        langs = detect_languages(paths)
        primaries = [l for l in langs if l.primary]
        self.assertEqual(len(primaries), 1)
        self.assertEqual(primaries[0].name, "Python")

    def test_unknown_extensions_ignored(self):
        paths = ["image.png", "data.csv", "doc.pdf"]
        langs = detect_languages(paths)
        self.assertEqual(langs, [])

    def test_empty_list(self):
        langs = detect_languages([])
        self.assertEqual(langs, [])

    def test_file_count_accurate(self):
        paths = ["a.py", "b.py", "c.py", "d.go"]
        langs = detect_languages(paths)
        py = next(l for l in langs if l.name == "Python")
        self.assertEqual(py.file_count, 3)


class TestDetectFrameworks(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.root = Path(self.tmp)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_nextjs_from_file(self):
        (self.root / "next.config.js").write_text("module.exports={}", encoding="utf-8")
        result = detect_frameworks(self.root, [], {})
        self.assertIn("Next.js", result)

    def test_django_from_dependency(self):
        result = detect_frameworks(self.root, [], {"Django": ">=4.0"})
        self.assertIn("Django", result)

    def test_react_from_dependency(self):
        result = detect_frameworks(self.root, [], {"react": "^18.0"})
        self.assertIn("React", result)

    def test_fastapi_requires_dep(self):
        # manage.py without fastapi dep should NOT trigger FastAPI
        (self.root / "main.py").write_text("", encoding="utf-8")
        result = detect_frameworks(self.root, ["main.py"], {})
        self.assertNotIn("FastAPI", result)

    def test_no_false_positives_empty(self):
        result = detect_frameworks(self.root, [], {})
        self.assertEqual(result, [])

    def test_flutter_from_pubspec(self):
        (self.root / "pubspec.yaml").write_text("name: myapp", encoding="utf-8")
        result = detect_frameworks(self.root, [], {})
        self.assertIn("Flutter", result)


class TestDetectGit(unittest.TestCase):
    def test_non_git_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            is_git, branch, remote = detect_git(Path(tmp))
            self.assertFalse(is_git)
            self.assertIsNone(branch)
            self.assertIsNone(remote)

    def test_git_dir_branch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git_dir = root / ".git"
            git_dir.mkdir()
            (git_dir / "HEAD").write_text("ref: refs/heads/main\n", encoding="utf-8")
            is_git, branch, remote = detect_git(root)
            self.assertTrue(is_git)
            self.assertEqual(branch, "main")

    def test_git_config_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            git_dir = root / ".git"
            git_dir.mkdir()
            (git_dir / "HEAD").write_text("ref: refs/heads/dev\n", encoding="utf-8")
            (git_dir / "config").write_text(
                "[remote \"origin\"]\n\turl = https://github.com/user/repo.git\n",
                encoding="utf-8",
            )
            is_git, branch, remote = detect_git(root)
            self.assertTrue(is_git)
            self.assertEqual(branch, "dev")
            self.assertIn("github.com", remote)

    def test_detached_head(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".git").mkdir()
            (root / ".git" / "HEAD").write_text("abc1234abc\n", encoding="utf-8")
            is_git, branch, _ = detect_git(root)
            self.assertTrue(is_git)
            self.assertEqual(branch, "detached")


class TestDetectProjectName(unittest.TestCase):
    def test_uses_manifest_name(self):
        name = detect_project_name(Path("/some/path"), {"name": "my-app"})
        self.assertEqual(name, "my-app")

    def test_fallback_to_dir_name(self):
        name = detect_project_name(Path("/home/user/Projects/Nova"), {"name": ""})
        self.assertEqual(name, "Nova")

    def test_strips_whitespace(self):
        name = detect_project_name(Path("/tmp/proj"), {"name": "  myproj  "})
        self.assertEqual(name, "myproj")
