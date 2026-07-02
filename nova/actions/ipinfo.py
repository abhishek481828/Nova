import os
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.ipinfo import IpInfoService
from nova.logger import logger, log_error
from nova.services.nebius import call_nebius_llm
from nova.config import load_prompt, NEBIUS_API_KEY

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
            if NEBIUS_API_KEY:
                fallback_prompt = (
                    "You are Nova, a helpful voice assistant. Answer the user's IP or location info question naturally based on the provided IP details.\n"
                    "Rules:\n"
                    "1. Keep it concise, conversational, and direct.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Summarize the key location details naturally (e.g. say 'Your IP address is 8.8.8.8 located in Mountain View, California, registered under Google' instead of listing raw text)."
                )
                system_prompt = load_prompt("ipinfo_prompt.txt", fallback_prompt)
                summary = call_nebius_llm(
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"IP Geolocation data:\n{result_context}"}
                    ],
                    temperature=0.3
                )
                if summary:
                    return summary

            # Fallback if Nebius is unavailable: return raw formatted string
            return f"IP address details:\n\n" + result_context

        except Exception as e:
            log_error("IP details lookup failed", e)
            return f"IP details lookup failed: {e}"
