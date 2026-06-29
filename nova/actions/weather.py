import os
import urllib.request
import json
from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.services.weather import WeatherService
from nova.logger import logger

class WeatherAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "weather"

    def execute(self, params: Dict[str, Any]) -> str:
        location = params.get("location", "").strip()

        try:
            # 1. Run Weather Search
            service = WeatherService()
            data = service.get_current_weather(location)
            if not data:
                return "Failed to retrieve weather details."

            # 2. Format details
            weather_string = (
                f"Location: {data['name']}, {data['region']}, {data['country']}\n"
                f"Temperature: {data['temp_c']}°C ({data['temp_f']}°F)\n"
                f"Condition: {data['condition']}\n"
                f"Humidity: {data['humidity']}%\n"
                f"Wind: {data['wind_kph']} kph ({data['wind_mph']} mph)\n"
            )

            # 3. Call LLM (Nebius) to summarize naturally
            nebius_key = os.environ.get("NEBIUS_API_KEY")
            if nebius_key:
                nebius_url = "https://api.studio.nebius.ai/v1/chat/completions"
                system_prompt = (
                    "You are Nova, a helpful voice assistant. Answer the user's weather question naturally based on the provided weather data.\n"
                    "Rules:\n"
                    "1. Keep it concise, conversational, and direct.\n"
                    "2. Avoid using markdown formatting (like bullet points or bold text) since it might be spoken aloud.\n"
                    "3. Summarize the temperature, condition, and any other notable details naturally (e.g. say 'It is currently sunny and 22 degrees in London' instead of listing it as a block)."
                )
                payload = {
                    "model": "meta-llama/Llama-3.3-70B-Instruct",
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Weather data:\n{weather_string}"}
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
                    logger.error(f"Failed to generate Nebius summary for weather data: {e}")

            # Fallback if Nebius is unavailable: return raw formatted weather conditions
            return f"Current weather conditions:\n\n" + weather_string

        except Exception as e:
            return f"Weather execution failed: {e}"
