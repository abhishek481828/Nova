"""
Tests for unified diff generation.
"""
import unittest
from nova.edit.diff import generate_diff, apply_diff_preview

class TestDiffGeneration(unittest.TestCase):
    def test_diff_statistics(self):
        old = "line 1\nline 2\nline 3\n"
        new = "line 1\nline 2 modified\nline 3\nline 4\n"
        
        result = generate_diff(old, new, filename="test.txt")
        self.assertTrue(result.has_changes)
        self.assertFalse(result.is_empty)
        self.assertEqual(result.lines_added, 2)
        self.assertEqual(result.lines_removed, 1)
        self.assertIn("+line 2 modified", result.diff_text)
        self.assertIn("-line 2", result.diff_text)

    def test_no_changes(self):
        content = "line 1\nline 2\n"
        result = generate_diff(content, content)
        self.assertTrue(result.is_empty)
        self.assertEqual(result.lines_added, 0)
        self.assertEqual(result.lines_removed, 0)

    def test_apply_diff_preview(self):
        old = "hello\n"
        new = "world\n"
        preview = apply_diff_preview(old, new, "test.txt")
        self.assertIn("[ADD] world", preview)
        self.assertIn("[DEL] hello", preview)
