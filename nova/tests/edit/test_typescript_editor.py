"""
Tests for TypeScript/JavaScript regex-based editing.
"""
import unittest
from nova.edit.typescript_editor import rename_symbol_in_source, remove_function, insert_function, insert_import

class TestTypeScriptEditor(unittest.TestCase):
    def test_rename_symbol(self):
        src = (
            "const myVar = 10;\n"
            "function printVar() {\n"
            "  console.log(myVar);\n"
            "}\n"
        )
        renamed = rename_symbol_in_source(src, "myVar", "newName")
        self.assertIn("const newName = 10;", renamed)
        self.assertIn("console.log(newName);", renamed)
        self.assertNotIn("myVar", renamed)

    def test_remove_function(self):
        src = (
            "const a = 1;\n"
            "export function deleteMe(param) {\n"
            "  if (param) {\n"
            "    console.log('yes');\n"
            "  }\n"
            "}\n"
            "const b = 2;\n"
        )
        removed = remove_function(src, "deleteMe")
        self.assertIn("const a = 1;", removed)
        self.assertIn("const b = 2;", removed)
        self.assertNotIn("deleteMe", removed)

    def test_insert_function(self):
        src = (
            "function first() {\n"
            "  return 1;\n"
            "}\n"
            "function third() {\n"
            "  return 3;\n"
            "}\n"
        )
        new_func = "function second() {\n  return 2;\n}"
        inserted = insert_function(src, new_func, after_name="first")
        self.assertIn("function first()", inserted)
        self.assertIn("function second()", inserted)
        self.assertIn("function third()", inserted)

    def test_insert_import(self):
        src = (
            "import { useState } from 'react';\n"
            "\n"
            "const App = () => {};\n"
        )
        inserted = insert_import(src, "import { useEffect } from 'react';")
        lines = inserted.splitlines()
        self.assertEqual(lines[0], "import { useState } from 'react';")
        self.assertEqual(lines[1], "import { useEffect } from 'react';")
