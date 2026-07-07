"""Tests for nova.project.manifest"""
import json
import unittest
import tempfile
from pathlib import Path

from nova.project.manifest import (
    parse_package_json,
    parse_requirements_txt,
    parse_pom_xml,
    parse_composer_json,
    parse_manifest,
    MANIFEST_PARSERS,
)


class TestParsePackageJson(unittest.TestCase):
    def _write(self, tmp, data):
        p = Path(tmp) / "package.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        return p

    def test_basic(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, {
                "name": "my-app",
                "version": "1.2.3",
                "dependencies": {"react": "^18.0", "axios": "^1.0"},
                "devDependencies": {"vite": "^4.0"},
            })
            result = parse_package_json(p)
        self.assertEqual(result["name"], "my-app")
        self.assertEqual(result["version"], "1.2.3")
        self.assertIn("react", result["dependencies"])
        self.assertIn("vite", result["dev_dependencies"])

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "package.json"
            p.write_text("{}", encoding="utf-8")
            result = parse_package_json(p)
        self.assertEqual(result["dependencies"], {})

    def test_missing_file(self):
        result = parse_manifest(Path("/nonexistent/package.json"))
        self.assertEqual(result["dependencies"], {})


class TestParseRequirementsTxt(unittest.TestCase):
    def _write(self, tmp, content):
        p = Path(tmp) / "requirements.txt"
        p.write_text(content, encoding="utf-8")
        return p

    def test_basic(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "flask>=2.0\nrequests==2.28.0\nnumpy\n")
            result = parse_requirements_txt(p)
        self.assertIn("flask", result["dependencies"])
        self.assertIn("requests", result["dependencies"])
        self.assertIn("numpy", result["dependencies"])

    def test_comments_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "# this is a comment\nfastapi\n")
            result = parse_requirements_txt(p)
        self.assertNotIn("# this is a comment", result["dependencies"])
        self.assertIn("fastapi", result["dependencies"])

    def test_flags_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "-r base.txt\ncelery\n")
            result = parse_requirements_txt(p)
        self.assertIn("celery", result["dependencies"])
        self.assertNotIn("-r base.txt", result["dependencies"])

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = self._write(tmp, "")
            result = parse_requirements_txt(p)
        self.assertEqual(result["dependencies"], {})


class TestParsePomXml(unittest.TestCase):
    POM = """
    <project>
      <artifactId>my-service</artifactId>
      <version>1.0.0</version>
      <dependencies>
        <dependency>
          <groupId>org.springframework</groupId>
          <artifactId>spring-core</artifactId>
          <version>5.3.0</version>
        </dependency>
      </dependencies>
    </project>
    """

    def test_basic(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "pom.xml"
            p.write_text(self.POM, encoding="utf-8")
            result = parse_pom_xml(p)
        self.assertEqual(result["name"], "my-service")
        self.assertIn("org.springframework:spring-core", result["dependencies"])


class TestParseComposerJson(unittest.TestCase):
    def test_basic(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "composer.json"
            p.write_text(json.dumps({
                "name": "vendor/project",
                "require": {"laravel/framework": "^10.0"},
                "require-dev": {"phpunit/phpunit": "^10"},
            }), encoding="utf-8")
            result = parse_composer_json(p)
        self.assertEqual(result["name"], "vendor/project")
        self.assertIn("laravel/framework", result["dependencies"])
        self.assertIn("phpunit/phpunit", result["dev_dependencies"])


class TestManifestDispatcher(unittest.TestCase):
    def test_all_known_manifests_have_parsers(self):
        expected = {
            "package.json", "requirements.txt", "pyproject.toml",
            "Cargo.toml", "pom.xml", "composer.json",
        }
        self.assertEqual(set(MANIFEST_PARSERS.keys()), expected)

    def test_unknown_file_returns_empty(self):
        result = parse_manifest(Path("/tmp/unknown.xyz"))
        self.assertEqual(result["dependencies"], {})
        self.assertEqual(result["dev_dependencies"], {})
