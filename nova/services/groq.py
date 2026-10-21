"""Groq Cloud LLM Integration for Nova Core."""

import json
from typing import List, Dict, Any, Optional
import httpx
from nova.logger import logger, log_error

FALLBACK_MODELS = ["openai/gpt-oss-20b", "qwen/qwen3.8-27b", "openai/gpt-oss-120b"]

def call_groq_llm(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.0,
    timeout: float = 15.0
) -> Optional[str]:
    """Calls Groq OpenAI-compatible chat completions API with automatic model fallback."""
    from nova.config import GROQ_API_KEY, GROQ_MODEL
    api_key = GROQ_API_KEY
    if not api_key:
        return None

    # Prepare model candidates: configured model first, followed by fallbacks
    preferred_model = model or GROQ_MODEL or "openai/gpt-oss-20b"
    models_to_try = [preferred_model]
    for m in FALLBACK_MODELS:
        if m not in models_to_try:
            models_to_try.append(m)

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    # Ensure system prompt or any message mentions JSON for json_object response format
    # Check if 'json' is in messages
    has_json_mention = any("json" in m.get("content", "").lower() for m in messages)
    clean_messages = list(messages)
    if not has_json_mention and clean_messages:
        clean_messages[-1] = {
            **clean_messages[-1],
            "content": clean_messages[-1].get("content", "") + "\nRespond with valid JSON."
        }

    for current_model in models_to_try:
        payload = {
            "model": current_model,
            "messages": clean_messages,
            "temperature": temperature,
            "response_format": {"type": "json_object"}
        }

        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=payload, headers=headers)
                if resp.status_code == 200:
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        if content:
                            return content
                elif resp.status_code == 429:
                    logger.debug(
                        f"Groq rate limit reached for model '{current_model}'. "
                        f"Falling back to next available model..."
                    )
                    continue
                else:
                    logger.debug(f"Groq API ({current_model}) returned status {resp.status_code}: {resp.text}")
        except Exception as e:
            log_error(f"Groq API call failed for model '{current_model}'", e)

    return None
