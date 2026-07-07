import unittest
from unittest.mock import MagicMock, patch
from nova.actions.chatgpt import ChatGPTAction

class TestChatGPTAction(unittest.TestCase):
    @patch("nova.actions.chatgpt.ChatGPTManager")
    def test_execute_open(self, mock_manager):
        mock_manager.execute_workflow.return_value = "Focused existing ChatGPT tab."
        action = ChatGPTAction()
        
        result = action.execute({"operation": "open"})
        
        self.assertEqual(result, "Focused existing ChatGPT tab.")
        mock_manager.execute_workflow.assert_called_once_with("open", "")

    @patch("nova.actions.chatgpt.ChatGPTManager")
    def test_execute_ask(self, mock_manager):
        mock_manager.execute_workflow.return_value = "Here is the quicksort code..."
        
        action = ChatGPTAction()
        result = action.execute({"operation": "ask", "prompt": "quicksort in python"})
        
        self.assertEqual(result, "Here is the quicksort code...")
        mock_manager.execute_workflow.assert_called_once_with("ask", "quicksort in python")

    @patch("nova.actions.chatgpt.ChatGPTManager")
    def test_execute_new_chat(self, mock_manager):
        mock_manager.execute_workflow.return_value = "Started a new ChatGPT conversation."
        action = ChatGPTAction()
        
        result = action.execute({"operation": "new_chat"})
        
        self.assertEqual(result, "Started a new ChatGPT conversation.")
        mock_manager.execute_workflow.assert_called_once_with("new_chat", "")
