"""
Unit tests for nova.session.intent_resolver.
"""
import unittest

from nova.session.intent_resolver import resolve_intent, is_followup
from nova.session.models import FollowupIntent


class TestIntentResolver(unittest.TestCase):

    # ── Undo ─────────────────────────────────────────────────────────────────

    def test_undo_basic(self):
        self.assertEqual(resolve_intent("undo"), FollowupIntent.UNDO)

    def test_undo_variants(self):
        phrases = [
            "undo that",
            "undo last",
            "undo it",
            "undo the last change",
            "undo the last edit",
            "undo the last task",
            "revert",
            "revert that",
            "revert last",
            "go back",
            "take that back",
            "rollback",
            "roll it back",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(
                    resolve_intent(phrase),
                    FollowupIntent.UNDO,
                    msg=f"Expected UNDO for: {phrase!r}",
                )

    # ── Redo ─────────────────────────────────────────────────────────────────

    def test_redo_basic(self):
        self.assertEqual(resolve_intent("redo"), FollowupIntent.REDO)

    def test_redo_variants(self):
        phrases = ["redo that", "redo it", "redo last"]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_intent(phrase), FollowupIntent.REDO)

    # ── Continue ─────────────────────────────────────────────────────────────

    def test_continue_basic(self):
        self.assertEqual(resolve_intent("continue"), FollowupIntent.CONTINUE)

    def test_continue_variants(self):
        phrases = [
            "continue please",
            "keep going",
            "go on",
            "proceed",
            "next step",
            "carry on",
            "finish it",
            "finish up",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_intent(phrase), FollowupIntent.CONTINUE)

    # ── Explain ──────────────────────────────────────────────────────────────

    def test_explain_basic(self):
        self.assertEqual(resolve_intent("explain"), FollowupIntent.EXPLAIN)

    def test_explain_variants(self):
        phrases = [
            "explain that",
            "explain again",
            "what did you do",
            "what did you create",
            "what did you change",
            "how does it work",
            "walk me through it",
            "describe the change",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_intent(phrase), FollowupIntent.EXPLAIN)

    # ── Improve ──────────────────────────────────────────────────────────────

    def test_improve_variants(self):
        phrases = ["improve", "improve it", "make it better", "enhance it"]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_intent(phrase), FollowupIntent.IMPROVE)

    # ── Refactor ─────────────────────────────────────────────────────────────

    def test_refactor_variants(self):
        phrases = ["refactor", "refactor it", "clean it up", "clean up the code"]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_intent(phrase), FollowupIntent.REFACTOR)

    # ── Add Tests ────────────────────────────────────────────────────────────

    def test_add_tests_variants(self):
        phrases = [
            "add tests",
            "add test",
            "write tests",
            "write unit tests",
            "generate tests",
            "create tests",
            "test it",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_intent(phrase), FollowupIntent.ADD_TESTS)

    # ── Optimize ─────────────────────────────────────────────────────────────

    def test_optimize_variants(self):
        phrases = [
            "optimize",
            "optimize it",
            "make it faster",
            "improve performance",
            "speed it up",
            "make it more efficient",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_intent(phrase), FollowupIntent.OPTIMIZE)

    # ── Document ─────────────────────────────────────────────────────────────

    def test_document_variants(self):
        phrases = [
            "document it",
            "add docs",
            "add docstrings",
            "write docs",
            "generate docs",
            "add comments",
            "document the code",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_intent(phrase), FollowupIntent.DOCUMENT)

    # ── NONE (pass-through) ───────────────────────────────────────────────────

    def test_none_for_unknown_phrases(self):
        phrases = [
            "add JWT authentication",
            "create a login page",
            "implement CRUD APIs",
            "fix the failing tests",
            "hello",
            "",
            "   ",
            "what is the capital of France",
        ]
        for phrase in phrases:
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_intent(phrase), FollowupIntent.NONE)

    # ── Case insensitivity ────────────────────────────────────────────────────

    def test_case_insensitive(self):
        self.assertEqual(resolve_intent("UNDO"), FollowupIntent.UNDO)
        self.assertEqual(resolve_intent("Continue PLEASE"), FollowupIntent.CONTINUE)
        self.assertEqual(resolve_intent("EXPLAIN THAT"), FollowupIntent.EXPLAIN)

    # ── Trailing punctuation stripped ────────────────────────────────────────

    def test_trailing_punctuation_stripped(self):
        self.assertEqual(resolve_intent("undo!"), FollowupIntent.UNDO)
        self.assertEqual(resolve_intent("continue."), FollowupIntent.CONTINUE)
        self.assertEqual(resolve_intent("explain?"), FollowupIntent.EXPLAIN)

    # ── is_followup helper ────────────────────────────────────────────────────

    def test_is_followup_true(self):
        self.assertTrue(is_followup("undo"))
        self.assertTrue(is_followup("continue"))
        self.assertTrue(is_followup("add tests"))

    def test_is_followup_false(self):
        self.assertFalse(is_followup("add JWT authentication"))
        self.assertFalse(is_followup(""))
