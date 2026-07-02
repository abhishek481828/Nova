import os
import json
import time
import urllib.request
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
    nebius_key = os.environ.get("NEBIUS_API_KEY")
    if not nebius_key:
        return None

    nebius_url = "https://api.studio.nebius.ai/v1/chat/completions"
    payload = {
        "model": model,
        "messages": messages,
        "temperature": temperature
    }

    for attempt in range(retries):
        try:
            req = urllib.request.Request(
                nebius_url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {nebius_key}"
                },
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                if resp.status == 200:
                    resp_data = json.loads(resp.read().decode("utf-8"))
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
