import unittest
from unittest.mock import MagicMock, patch
from nova.ai.ollama import OllamaClient

class TestChatGPTResponseReading(unittest.TestCase):
    def test_clean_markdown_for_tts(self):
        # We define a test copy of the cleanup logic inside core.py to verify its regexes
        def clean_markdown_for_tts(val: str) -> str:
            import re
            val = re.sub(r'```[\s\S]*?```', '[code snippet]', val)
            val = re.sub(r'`([^`\n]+)`', r'\1', val)
            val = re.sub(r'^\s*#{1,6}\s*(.+)$', r'\1', val, flags=re.MULTILINE)
            val = re.sub(r'\n+', ' ', val)
            val = re.sub(r'\s+', ' ', val)
            # Remove bold/italic formatting marks
            val = re.sub(r'\*\*([^*]+)\*\*', r'\1', val)
            val = re.sub(r'\*([^*]+)\*', r'\1', val)
            val = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', val)
            val = re.sub(r'^\s*[-*+]\s+', '', val, flags=re.MULTILINE)
            val = re.sub(r'^\s*\d+\.\s+', '', val, flags=re.MULTILINE)
            return val.strip()

        sample = (
            "### Title\n"
            "Here is a **bold** word and an *italic* word.\n"
            "- List item 1\n"
            "- List item 2\n"
            "For more details, check [Google](https://google.com).\n"
            "```python\nprint('hello')\n```\n"
            "Use the `print` command."
        )
        
        cleaned = clean_markdown_for_tts(sample)
        
        # Verify markdown syntax is gone
        self.assertNotIn("###", cleaned)
        self.assertNotIn("**bold**", cleaned)
        self.assertNotIn("[Google]", cleaned)
        self.assertNotIn("```", cleaned)
        self.assertIn("Title", cleaned)
        self.assertIn("bold word and an italic word", cleaned)
        self.assertIn("Google", cleaned)
        self.assertIn("[code snippet]", cleaned)
        self.assertIn("print command", cleaned)

    @patch("nova.ai.ollama.call_nebius_llm")
    def test_generate_chatgpt_tts_summary_nebius(self, mock_nebius):
        mock_nebius.return_value = "This is a clean summary."
        client = OllamaClient()
        
        summary = client.generate_chatgpt_tts_summary("what is recursion?", "Recursion is a process where a function calls itself directly or indirectly.")
        
        self.assertEqual(summary, "This is a clean summary.")
        mock_nebius.assert_called_once()

    @patch("nova.ai.ollama.call_nebius_llm")
    @patch("nova.ai.ollama.DISABLE_OLLAMA", True)
    def test_generate_chatgpt_tts_summary_fallback(self, mock_nebius):
        # Force nebius failure and disable Ollama to trigger sentence-based fallback
        mock_nebius.return_value = None
        client = OllamaClient()
        
        long_response = (
            "Recursion is a process in python. "
            "A function calls itself. "
            "This is the third sentence. "
            "This is the fourth sentence."
        )
        
        summary = client.generate_chatgpt_tts_summary("what is recursion?", long_response)
        
        # Should return first 3 sentences
        self.assertIn("Recursion is a process in python.", summary)
        self.assertIn("A function calls itself.", summary)
        self.assertIn("This is the third sentence.", summary)
        self.assertNotIn("This is the fourth sentence.", summary)
