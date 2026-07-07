import unittest
from unittest.mock import MagicMock
from nova.ai.prompt_enhancer import PromptEnhancer
from nova.ai.prompt_validator import PromptValidator

class TestPromptEnhancer(unittest.TestCase):
    def test_prompt_validator_validate(self):
        self.assertTrue(PromptValidator.validate("test"))
        self.assertFalse(PromptValidator.validate(""))
        self.assertFalse(PromptValidator.validate("   "))
        self.assertFalse(PromptValidator.validate(None))

    def test_prompt_validator_is_simple(self):
        # Short / simple
        self.assertTrue(PromptValidator.is_simple("hi"))
        self.assertTrue(PromptValidator.is_simple("how are you"))
        self.assertTrue(PromptValidator.is_simple("what is 5+5"))
        
        # Long or complex keywords
        self.assertFalse(PromptValidator.is_simple("write a python script to implement binary search"))
        self.assertFalse(PromptValidator.is_simple("explain quicksort algorithm time complexity"))

    def test_prompt_validator_continuation_keywords(self):
        for kw in ("continue", "explain more", "summarize", "simplify", "give example", "new chat", "start a new chat", "clear chat"):
            self.assertTrue(PromptValidator.is_simple(kw))
            self.assertTrue(PromptValidator.is_simple(f"  {kw}  "))

    def test_enhance_empty(self):
        enhancer = PromptEnhancer(ai_client=MagicMock())
        self.assertEqual(enhancer.enhance(""), "")
        self.assertEqual(enhancer.enhance("   "), "")

    def test_enhance_calls_ai_client_for_complex_prompt(self):
        mock_client = MagicMock()
        mock_client.enhance_prompt.return_value = "Please write a clean, well-commented implementation of the Quicksort algorithm in Python."
        
        enhancer = PromptEnhancer(ai_client=mock_client)
        # Complex prompt
        result = enhancer.enhance("write a python script to implement quicksort")
        
        self.assertEqual(result, "Please write a clean, well-commented implementation of the Quicksort algorithm in Python.")
        mock_client.enhance_prompt.assert_called_once_with("write a python script to implement quicksort")

    def test_enhance_bypasses_for_simple_prompt(self):
        mock_client = MagicMock()
        enhancer = PromptEnhancer(ai_client=mock_client)
        
        # Simple prompt should bypass
        result = enhancer.enhance("what is 5+5")
        
        self.assertEqual(result, "what is 5+5")
        mock_client.enhance_prompt.assert_not_called()

    def test_enhance_bypasses_for_continuation_keywords(self):
        mock_client = MagicMock()
        enhancer = PromptEnhancer(ai_client=mock_client)
        
        result = enhancer.enhance("explain more")
        self.assertEqual(result, "explain more")
        mock_client.enhance_prompt.assert_not_called()

    def test_enhance_fallback_on_exception(self):
        mock_client = MagicMock()
        mock_client.enhance_prompt.side_effect = Exception("LLM connection error")
        
        enhancer = PromptEnhancer(ai_client=mock_client)
        # Should gracefully fall back to original prompt for complex prompt
        result = enhancer.enhance("explain the quicksort algorithm in detail")
        self.assertEqual(result, "explain the quicksort algorithm in detail")
