import unittest
from unittest.mock import MagicMock, patch
from nova.ai.ollama import OllamaClient
from nova.ai.prompt_validator import PromptValidator

class TestSmartContextDetection(unittest.TestCase):
    @patch("nova.core.memory.HistoryManager.load_history")
    @patch("nova.ai.ollama.call_nebius_llm")
    def test_smart_context_flow(self, mock_nebius, mock_load_history):
        client = OllamaClient()

        # Step 1: Open ChatGPT
        # History is empty initially
        mock_load_history.return_value = []
        mock_nebius.return_value = '{"action": "chatgpt_action", "operation": "open"}'
        
        res = client.parse_intent("Open ChatGPT")
        self.assertIn("chatgpt_action", res)
        
        # Step 2: Ask recursion (without explicit prefix) while ChatGPT is active
        # Set history to indicate ChatGPT is the last active tool
        mock_load_history.return_value = [
            {
                "user_input": "Open ChatGPT",
                "parsed_action": {"action": "chatgpt_action", "operation": "open"},
                "status": "success",
                "result_message": "Focused existing ChatGPT tab."
            }
        ]
        
        # Mock LLM to return chatgpt_action with prompt
        mock_nebius.return_value = '{"action": "chatgpt_action", "operation": "ask", "prompt": "What is recursion?"}'
        res = client.parse_intent("What is recursion?")
        self.assertIn("chatgpt_action", res)
        self.assertIn("ask", res)
        
        # Verify the prompt context includes the system instructions
        call_args = mock_nebius.call_args[1]
        messages = call_args["messages"]
        system_msg = messages[0]["content"]
        self.assertIn("Active Tool Rule", system_msg)

        # Step 3: Explain more (ambiguous shortcut)
        mock_load_history.return_value.append({
            "user_input": "What is recursion?",
            "parsed_action": {"action": "chatgpt_action", "operation": "ask", "prompt": "What is recursion?"},
            "status": "success",
            "result_message": "Recursion is a process..."
        })
        
        mock_nebius.return_value = '{"action": "chatgpt_action", "operation": "ask", "prompt": "Explain more"}'
        res = client.parse_intent("Explain more")
        self.assertIn("chatgpt_action", res)
        
        # Step 4: Switch to YouTube
        mock_load_history.return_value.append({
            "user_input": "Explain more",
            "parsed_action": {"action": "chatgpt_action", "operation": "ask", "prompt": "Explain more"},
            "status": "success",
            "result_message": "Sure, recursion can be compared to..."
        })
        
        # Switched tool specifically to YouTube
        mock_nebius.return_value = '{"action": "chromium_action", "operation": "search_youtube", "query": "recursion explained"}'
        res = client.parse_intent("Open YouTube")
        self.assertIn("chromium_action", res)
        self.assertIn("search_youtube", res)

        # Step 5: Continue (ambiguous, active tool is now chromium, should NOT route to ChatGPT)
        mock_load_history.return_value.append({
            "user_input": "Open YouTube",
            "parsed_action": {"action": "chromium_action", "operation": "search_youtube", "query": "recursion explained"},
            "status": "success",
            "result_message": "Opened YouTube searching for recursion."
        })
        
        # Since active tool is chromium_action, it should not default back to ChatGPT unless specified
        mock_nebius.return_value = '{"action": "chat_response", "message": "What would you like me to continue with?"}'
        res = client.parse_intent("Continue")
        self.assertIn("chat_response", res)

    def test_ambiguous_prompts_validator(self):
        # Ambiguous prompts that bypass LLM enhancement to allow execution using ChatGPT's previous context
        ambiguous = ["continue", "explain more", "summarize", "simplify", "give example"]
        for p in ambiguous:
            self.assertTrue(PromptValidator.is_simple(p))
