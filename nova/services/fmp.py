import os
import time
import httpx
from nova.logger import logger

# In-memory cache
_cache = {}
CACHE_TTL = 600  # 10 minutes (stock quotes change throughout the day)

class FmpService:
    def __init__(self):
        self.api_key = os.environ.get("FMP_API_KEY")
        self.base_url = "https://financialmodelingprep.com/stable"

    def get_stock_quote(self, symbol: str) -> dict:
        """
        Retrieves real-time stock quote details for a symbol from FMP stable API.
        """
        if not self.api_key:
            logger.error("FMP API key is missing. Set FMP_API_KEY in your .env file.")
            raise ValueError("FMP API key is not configured.")

        symbol_clean = symbol.upper().strip()
        cache_key = f"quote:{symbol_clean}"

        # Check cache
        if cache_key in _cache:
            timestamp, cached_data = _cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                logger.info(f"FMP Cache Hit for: {cache_key}")
                return cached_data

        url = f"{self.base_url}/quote"
        params = {
            "symbol": symbol_clean,
            "apikey": self.api_key
        }

        retries = 2
        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                logger.info(f"FMP API Request (attempt {attempt + 1}) for stock: {symbol_clean}")
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    
                    if not isinstance(data, list) or len(data) == 0:
                        raise Exception(f"No stock quote returned for symbol '{symbol_clean}'.")
                    
                    quote_data = data[0]
                    # Cache result
                    _cache[cache_key] = (time.time(), quote_data)
                    return quote_data

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403):
                    logger.error(f"FMP API Authentication / Subscription error ({status_code}): {e.response.text}")
                    raise Exception("FMP API Authentication or Endpoint permissions failed.")
                if status_code >= 500 and attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"FMP API returned status code {status_code}: {e.response.text}")
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"FMP API network/timeout error: {e}")
            except Exception as e:
                raise Exception(f"Unexpected error during FMP lookup: {e}")
        return {}
