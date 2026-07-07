"""
Tests for Python AST-based editing.
"""
import unittest
from nova.edit.python_editor import rename_symbol_in_source, remove_function, insert_function, insert_import

class TestPythonEditor(unittest.TestCase):
    def test_rename_symbol(self):
        src = (
            "class MyClass:\n"
            "    def my_method(self, value):\n"
            "        return value\n"
            "val = MyClass().my_method(10)\n"
        )
        # Rename my_method -> new_method_name
        renamed = rename_symbol_in_source(src, "my_method", "new_method_name")
        self.assertIn("def new_method_name(self, value):", renamed)
        self.assertIn("MyClass().new_method_name(10)", renamed)
        self.assertNotIn("my_method", renamed)

    def test_remove_function(self):
        src = (
            "def foo():\n"
            "    return 'foo'\n"
            "\n"
            "@decorator\n"
            "def bar():\n"
            "    return 'bar'\n"
            "\n"
            "def baz():\n"
            "    return 'baz'\n"
        )
        # Remove bar
        removed = remove_function(src, "bar")
        self.assertIn("def foo():", removed)
        self.assertIn("def baz():", removed)
        self.assertNotIn("def bar():", removed)
        self.assertNotIn("@decorator", removed)

    def test_insert_function(self):
        src = (
            "def foo():\n"
            "    return 'foo'\n"
        )
        new_func = "def bar():\n    return 'bar'"
        inserted = insert_function(src, new_func, after_name="foo")
        self.assertIn("def foo():", inserted)
        self.assertIn("def bar():", inserted)
        
        # Test appending to the end
        inserted_end = insert_function(src, new_func)
        self.assertTrue(inserted_end.endswith("def bar():\n    return 'bar'\n"))

    def test_insert_import(self):
        src = (
            "import os\n"
            "from sys import exit\n"
            "\n"
            "print('hello')\n"
        )
        inserted = insert_import(src, "import math")
        self.assertIn("import math", inserted)
        
        # Verify it places after imports
        lines = inserted.splitlines()
        self.assertEqual(lines[0], "import os")
        self.assertEqual(lines[1], "from sys import exit")
        self.assertEqual(lines[2], "import math")
