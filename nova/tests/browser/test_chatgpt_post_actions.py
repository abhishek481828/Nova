import os
import unittest
from unittest.mock import MagicMock, patch
from nova.browser.chatgpt_manager import ChatGPTManager

class TestChatGPTPostActions(unittest.TestCase):
    def setUp(self):
        # Reset cache before each test
        ChatGPTManager._last_received_response = None
        self.txt_path = "/home/nixos/Projects/Nova/chatgpt_response.txt"
        self.md_path = "/home/nixos/Projects/Nova/chatgpt_response.md"
        self.pdf_path = "/home/nixos/Projects/Nova/chatgpt_response.pdf"
        
        # Clean files
        for p in (self.txt_path, self.md_path, self.pdf_path):
            if os.path.exists(p):
                os.remove(p)

    def tearDown(self):
        # Clean files
        for p in (self.txt_path, self.md_path, self.pdf_path):
            if os.path.exists(p):
                os.remove(p)

    def test_post_actions_no_cache_error(self):
        res = ChatGPTManager.execute_workflow("copy", "")
        self.assertIn("Error: No cached ChatGPT response", res)

        res = ChatGPTManager.execute_workflow("save", "")
        self.assertIn("Error: No cached ChatGPT response", res)

        res = ChatGPTManager.execute_workflow("export_md", "")
        self.assertIn("Error: No cached ChatGPT response", res)

        res = ChatGPTManager.execute_workflow("export_pdf", "")
        self.assertIn("Error: No cached ChatGPT response", res)

        res = ChatGPTManager.execute_workflow("summarize_response", "")
        self.assertIn("Error: No cached ChatGPT response", res)

        res = ChatGPTManager.execute_workflow("translate_response", "")
        self.assertIn("Error: No cached ChatGPT response", res)

    @patch("nova.browser.chatgpt_manager.ChatGPTManager._copy_to_clipboard")
    def test_copy_action_success(self, mock_copy):
        mock_copy.return_value = True
        ChatGPTManager._last_received_response = "Cached content details."
        
        res = ChatGPTManager.execute_workflow("copy", "")
        
        self.assertEqual(res, "Copied response to clipboard.")
        mock_copy.assert_called_once_with("Cached content details.")

    def test_save_and_export_md_actions(self):
        ChatGPTManager._last_received_response = "Clean markdown content."
        
        res_save = ChatGPTManager.execute_workflow("save", "")
        self.assertIn("Saved response to", res_save)
        self.assertTrue(os.path.exists(self.txt_path))
        with open(self.txt_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "Clean markdown content.")

        res_md = ChatGPTManager.execute_workflow("export_md", "")
        self.assertIn("Exported response as Markdown", res_md)
        self.assertTrue(os.path.exists(self.md_path))
        with open(self.md_path, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "Clean markdown content.")

    @patch("nova.browser.chatgpt_manager.BrowserRunner")
    def test_export_pdf_action(self, mock_runner):
        # Mock BrowserRunner execution to simulate PDF creation
        def mock_execute(func, *args, **kwargs):
            # Create a mock empty file to simulate output creation
            with open(self.pdf_path, "w") as f:
                f.write("mock pdf contents")
            return None
        mock_runner.execute.side_effect = mock_execute
        
        ChatGPTManager._last_received_response = "PDF print body."
        
        res = ChatGPTManager.execute_workflow("export_pdf", "")
        
        self.assertIn("Exported response as PDF", res)
        self.assertTrue(os.path.exists(self.pdf_path))

    @patch("nova.ai.ollama.OllamaClient.generate_chatgpt_tts_summary")
    def test_summarize_action(self, mock_summary):
        mock_summary.return_value = "Brief summary."
        ChatGPTManager._last_received_response = "Detailed response information that is very long."
        
        res = ChatGPTManager.execute_workflow("summarize_response", "")
        
        self.assertEqual(res, "Summary of response: Brief summary.")
        mock_summary.assert_called_once_with("summarize", "Detailed response information that is very long.")

    @patch("nova.ai.ollama.OllamaClient.translate_text")
    def test_translate_action(self, mock_translate):
        mock_translate.return_value = "Hola Mundo"
        ChatGPTManager._last_received_response = "Hello World"
        
        res = ChatGPTManager.execute_workflow("translate_response", "Spanish")
        
        self.assertEqual(res, "Translation (Spanish): Hola Mundo")
        mock_translate.assert_called_once_with("Hello World", "Spanish")
