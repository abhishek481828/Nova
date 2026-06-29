import os
import time
import httpx
from nova.logger import logger

# In-memory cache
_cache = {}
CACHE_TTL = 86400  # 24 hours (IP locations change very rarely)

class IpInfoService:
    def __init__(self):
        self.api_key = os.environ.get("IPINFO_API_KEY")
        self.base_url = "https://ipinfo.io"

    def get_ip_info(self, ip_address: str = "") -> dict:
        """
        Queries IPinfo.io for details about an IP address (or current client IP if empty).
        """
        if not self.api_key:
            logger.error("IPinfo API key is missing. Set IPINFO_API_KEY in your .env file.")
            raise ValueError("IPinfo API key is not configured.")

        ip_clean = ip_address.strip()
        cache_key = ip_clean if ip_clean else "current_ip"

        # Check cache
        if cache_key in _cache:
            timestamp, cached_data = _cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                logger.info(f"IPinfo Cache Hit for: {cache_key}")
                return cached_data

        # Construct endpoint URL
        endpoint = f"/{ip_clean}/json" if ip_clean else "/json"
        url = f"{self.base_url}{endpoint}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Accept": "application/json"
        }

        retries = 2
        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                logger.info(f"IPinfo.io API Request (attempt {attempt + 1}) for: {cache_key}")
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(url, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    
                    # Store only relevant fields to return clean data
                    ip_data = {
                        "ip": data.get("ip", ""),
                        "hostname": data.get("hostname", "N/A"),
                        "city": data.get("city", "Unknown City"),
                        "region": data.get("region", "Unknown Region"),
                        "country": data.get("country", "Unknown Country"),
                        "loc": data.get("loc", "N/A"),
                        "org": data.get("org", "N/A"),
                        "postal": data.get("postal", "N/A"),
                        "timezone": data.get("timezone", "N/A")
                    }

                    # Cache result
                    _cache[cache_key] = (time.time(), ip_data)
                    return ip_data

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403):
                    logger.error(f"IPinfo.io API Authentication / Rate limit error ({status_code}): {e.response.text}")
                    raise Exception("IPinfo.io API Authentication failed.")
                if status_code >= 500 and attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"IPinfo.io API returned status code {status_code}: {e.response.text}")
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"IPinfo.io API network/timeout error: {e}")
            except Exception as e:
                raise Exception(f"Unexpected error during IP lookup: {e}")
        return {}
