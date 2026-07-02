import os
import json
import time
from typing import List, Dict, Any, Optional
from nova.logger import logger

def call_nebius_llm(
    messages: List[Dict[str, str]],
    model: str = "meta-llama/Llama-3.3-70B-Instruct",
    temperature: float = 0.3,
    timeout: float = 15.0,
    retries: int = 1,
    backoff: float = 1.0
) -> Optional[str]:
    """
    Consolidated helper to call the Nebius chat completion API.
    Provides standard retry mechanism, error logging, and payload mapping.
    """
    from nova.config import NEBIUS_API_KEY
    nebius_key = NEBIUS_API_KEY
    if not nebius_key:
        return None

    nebius_url = "https://api.studio.nebius.ai/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }

    import httpx
    for attempt in range(retries):
        try:
            with httpx.Client() as client:
                resp = client.post(
                    nebius_url,
                    json=payload,
                    headers={
                        "Authorization": f"Bearer {nebius_key}"
                    },
                    timeout=timeout
                )
                if resp.status_code == 200:
                    resp_data = resp.json()
                    choices = resp_data.get("choices", [])
                    if choices:
                        content = choices[0].get("message", {}).get("content", "")
                        return content.strip()
        except Exception as e:
            from nova.logger import log_error
            log_error(f"Nebius API call failed (attempt {attempt + 1}/{retries})", e)
            if attempt < retries - 1:
                time.sleep(backoff)
                backoff *= 2.0

    return None
