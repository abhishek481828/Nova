import os
import time
import httpx
from nova.logger import logger

# In-memory cache
_cache = {}
CACHE_TTL = 600  # 10 minutes

class WeatherService:
    def __init__(self):
        self.api_key = os.environ.get("WEATHER_API_KEY")
        self.base_url = "https://api.weatherapi.com/v1/current.json"

    def get_current_weather(self, location: str = "") -> dict:
        """
        Queries WeatherAPI.com for current conditions.
        Returns a dict with location and current weather info.
        """
        if not self.api_key:
            logger.error("Weather API key is missing. Set WEATHER_API_KEY in your .env file.")
            raise ValueError("Weather API key is not configured.")

        # Default to automatic IP location resolution if location is empty
        loc_query = location.strip() if location else "auto:ip"
        normalized_query = loc_query.lower()

        # Check cache
        if normalized_query in _cache:
            timestamp, cached_data = _cache[normalized_query]
            if time.time() - timestamp < CACHE_TTL:
                logger.info(f"Weather Cache Hit for: {loc_query}")
                return cached_data

        params = {
            "key": self.api_key,
            "q": loc_query,
            "aqi": "no"
        }

        retries = 2
        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                logger.info(f"Weather API Request (attempt {attempt + 1}) for: {loc_query}")
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(self.base_url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    
                    # Store only relevant fields to return clean data
                    location_info = data.get("location", {})
                    current_info = data.get("current", {})
                    condition_info = current_info.get("condition", {})
                    
                    weather_data = {
                        "name": location_info.get("name", ""),
                        "region": location_info.get("region", ""),
                        "country": location_info.get("country", ""),
                        "temp_c": current_info.get("temp_c", 0.0),
                        "temp_f": current_info.get("temp_f", 0.0),
                        "condition": condition_info.get("text", ""),
                        "humidity": current_info.get("humidity", 0),
                        "wind_kph": current_info.get("wind_kph", 0.0),
                        "wind_mph": current_info.get("wind_mph", 0.0)
                    }

                    # Cache the parsed results
                    _cache[normalized_query] = (time.time(), weather_data)
                    return weather_data

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403):
                    logger.error(f"Weather API Authentication error ({status_code}): {e.response.text}")
                    raise Exception("Weather API Authentication failed.")
                if status_code >= 500 and attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"Weather API returned status code {status_code}: {e.response.text}")
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"Weather API network/timeout error: {e}")
            except Exception as e:
                raise Exception(f"Unexpected error during weather lookup: {e}")
