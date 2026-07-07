"""
Tests for edit operations and history.
"""
import unittest
from nova.edit.operations import EditKind, EditOperation, EditHistory, EditResult

class TestEditOperations(unittest.TestCase):
    def test_edit_result_creation(self):
        res = EditResult.ok(message="Success", diff="some diff")
        self.assertTrue(res.success)
        self.assertEqual(res.message, "Success")
        self.assertEqual(res.diff, "some diff")

        res_fail = EditResult.fail(message="Failed")
        self.assertFalse(res_fail.success)
        self.assertEqual(res_fail.message, "Failed")

    def test_edit_operation_reversibility(self):
        op_create = EditOperation(kind=EditKind.CREATE, rel_path="a.py", old_content=None)
        self.assertFalse(op_create.is_reversible)

        op_update = EditOperation(kind=EditKind.UPDATE, rel_path="a.py", old_content="old", new_content="new")
        self.assertTrue(op_update.is_reversible)

    def test_edit_history_push_pop(self):
        history = EditHistory()
        history.clear()
        
        op1 = EditOperation(kind=EditKind.CREATE, rel_path="a.py", old_content=None)
        op2 = EditOperation(kind=EditKind.UPDATE, rel_path="b.py", old_content="old", new_content="new")
        
        history.push(op1)
        history.push(op2)
        
        self.assertEqual(len(history), 2)
        
        last = history.pop_last()
        self.assertIsNotNone(last)
        self.assertEqual(last.rel_path, "b.py")
        
        # op1 is not reversible, so pop_last should skip it and return None
        self.assertIsNone(history.pop_last())
        self.assertEqual(len(history), 0)
