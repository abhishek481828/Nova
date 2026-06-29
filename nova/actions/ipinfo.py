import os
import urllib.request
import json
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.ipinfo import IpInfoService
from nova.logger import logger

class IpInfoAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "ip_info"

    def execute(self, params: Dict[str, Any]) -> str:
        ip_address = params.get("ip_address", "").strip()

        try:
            service = IpInfoService()
            data = service.get_ip_info(ip_address)
            
            if not data:
                return "Failed to retrieve IP information details."

            result_context = (
                f"IP Address: {data['ip']}\n"
                f"Hostname: {data['hostname']}\n"
                f"City: {data['city']}\n"
                f"Region: {data['region']}\n"
                f"Country: {data['country']}\n"
                f"Location Coordinates: {data['loc']}\n"
                f"Organization/ISP: {data['org']}\n"
                f"Postal Code: {data['postal']}\n"
                f"Timezone: {data['timezone']}\n"
            )

            # 2. Call LLM (Nebius) to summarize naturally
            nebius_key = os.environ.get("NEBIUS_API_KEY")
            if nebius_key:
                nebius_url = "https://api.studio.nebius.ai/v1/chat/completions"
                system_prompt = (
                    "You are Nova, a helpful voice assistant. Answer the user's IP or location info question naturally based on the provided IP details.\n"
                    "Rules:\n"
                    "1. Keep it concise, conversational, and direct.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Summarize the key location details naturally (e.g. say 'Your IP address is 8.8.8.8 located in Mountain View, California, registered under Google' instead of listing raw text)."
                )
                payload = {
                    "model": "meta-llama/Llama-3.3-70B-Instruct",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"IP Geolocation data:\n{result_context}"}
                    ],
                    "temperature": 0.3
                }
                
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
                    with urllib.request.urlopen(req, timeout=15) as resp:
                        if resp.status == 200:
                            resp_data = json.loads(resp.read().decode("utf-8"))
                            choices = resp_data.get("choices", [])
                            if choices:
                                summary = choices[0].get("message", {}).get("content", "").strip()
                                if summary:
                                    return summary
                except Exception as e:
                    logger.error(f"Failed to generate Nebius summary for IP info: {e}")

            # Fallback if Nebius is unavailable: return raw formatted string
            return f"IP address details:\n\n" + result_context

        except Exception as e:
            return f"IP details lookup failed: {e}"
