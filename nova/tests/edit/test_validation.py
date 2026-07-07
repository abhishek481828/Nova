"""
Tests for syntax validation.
"""
import unittest
from nova.edit.validation import validate_file

class TestSyntaxValidation(unittest.TestCase):
    def test_validate_valid_python(self):
        src = "def add(a, b):\n    return a + b\n"
        res = validate_file("test.py", src)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.language, "Python")

    def test_validate_invalid_python(self):
        src = "def add(a, b\n    return a + b\n"
        res = validate_file("test.py", src)
        self.assertFalse(res.is_valid)
        self.assertEqual(len(res.errors), 1)
        self.assertIn("SyntaxError", res.errors[0])

    def test_validate_valid_typescript(self):
        src = "const myFunc = () => { return [1, 2, 3]; };"
        res = validate_file("test.ts", src)
        self.assertTrue(res.is_valid)
        self.assertEqual(res.language, "TypeScript")

    def test_validate_invalid_typescript_brackets(self):
        src = "const myFunc = () => { return [1, 2, 3;"
        res = validate_file("test.ts", src)
        self.assertFalse(res.is_valid)
        self.assertIn("missing closing bracket", res.errors[0].lower())

    def test_validate_mismatched_brackets(self):
        src = "const myFunc = () => { return (1, 2, 3]; };"
        res = validate_file("test.ts", src)
        self.assertFalse(res.is_valid)
        self.assertIn("mismatched", res.errors[0].lower())

    def test_validate_generic_always_passes(self):
        res = validate_file("config.yaml", "some: random: { bracket mismatched")
        self.assertTrue(res.is_valid)
