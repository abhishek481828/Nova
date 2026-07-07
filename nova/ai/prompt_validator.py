import re

class PromptValidator:
    """
    Validates prompts and determines if they are simple enough to bypass
    the Prompt Enhancer to minimize execution latency.
    """
    
    @staticmethod
    def validate(prompt: str) -> bool:
        """Returns True if the prompt is valid (non-empty and not just whitespace)."""
        return bool(prompt and prompt.strip())

    @staticmethod
    def is_simple(prompt: str) -> bool:
        """
        Determines if a prompt is simple (short and free of complex keywords).
        Simple prompts bypass LLM prompt enhancement to reduce response latency.
        """
        if not prompt:
            return True
            
        clean = prompt.strip().lower()
        
        # Direct continuation shortcuts bypass enhancement to preserve context
        CONTINUATION_KEYWORDS = {
            "continue", "explain more", "summarize", "simplify", "give example", 
            "new chat", "start a new chat", "clear chat"
        }
        if clean in CONTINUATION_KEYWORDS:
            return True
        
        # Simple prompts are typically short (under 5 words or 30 characters)
        words = clean.split()
        if len(words) < 5 or len(clean) < 30:
            # Check if it contains any key terms indicating a complex request
            COMPLEX_KEYWORDS = {
                "code", "write", "explain", "create", "how to", "implement", "function", 
                "python", "rust", "cpp", "c++", "javascript", "script", "algorithm", "quicksort",
                "summary", "draft", "essay", "analysis", "compare", "research", "diff"
            }
            # If none of the complex keywords are present, it is considered simple
            if not any(kw in clean for kw in COMPLEX_KEYWORDS):
                return True
                
        return False
