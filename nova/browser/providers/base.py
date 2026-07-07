from abc import ABC, abstractmethod
from typing import Optional

class AIProvider(ABC):
    """
    Interface defining core capabilities for an AI Provider in Nova.
    Allows ChatGPT, Claude, Gemini, Perplexity, Grok, or local Ollama
    to plug in seamlessly.
    """
    
    @classmethod
    @abstractmethod
    def initialize(cls) -> None:
        """Warms up and prepares the provider's active session/context."""
        pass

    @classmethod
    @abstractmethod
    def execute_action(cls, operation: str, prompt: str) -> str:
        """Executes an action (e.g. ask, search, copy, save, reset) using the provider."""
        pass

    @classmethod
    @abstractmethod
    def reset_session(cls) -> None:
        """Resets the active conversation or session state."""
        pass

    @classmethod
    @abstractmethod
    def close(cls) -> None:
        """Closes and releases any active resources associated with the provider."""
        pass
