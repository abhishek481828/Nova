from typing import Optional
from nova.ai.ollama import OllamaClient
from nova.ai.prompt_validator import PromptValidator

class PromptEnhancer:
    """
    Enhances raw user prompts to make them more descriptive and effective for ChatGPT,
    while retaining the user's original intent.
    """
    def __init__(self, ai_client: Optional[OllamaClient] = None) -> None:
        self.ai_client = ai_client or OllamaClient()

    def enhance(self, prompt: str) -> str:
        """
        Takes a raw query/prompt and returns the enhanced version using the active LLM client.
        If the prompt is invalid, returns empty string. If simple, bypasses enhancement.
        """
        if not PromptValidator.validate(prompt):
            return ""
            
        if PromptValidator.is_simple(prompt):
            # Bypass enhancement for simple prompts to reduce latency
            return prompt.strip()
            
        try:
            return self.ai_client.enhance_prompt(prompt)
        except Exception:
            # Fallback to the original prompt on failure
            return prompt
