import os
import time
import httpx
from nova.logger import logger
from nova.config import EXCHANGERATE_API_KEY

# In-memory cache
_cache = {}
CACHE_TTL = 3600  # 1 hour

class ExchangeRateService:
    def __init__(self):
        self.api_key = EXCHANGERATE_API_KEY
        self.base_url = "https://api.exchangerate.host"

    def convert(self, from_curr: str, to_curr: str, amount: float = 1.0) -> dict:
        """
        Converts an amount from one currency to another using the ExchangeRate.host API.
        """
        if not self.api_key:
            logger.error("ExchangeRate API key is missing. Set EXCHANGERATE_API_KEY in your .env file.")
            raise ValueError("ExchangeRate API key is not configured.")

        from_clean = from_curr.upper().strip()
        to_clean = to_curr.upper().strip()
        cache_key = f"convert:{from_clean}:{to_clean}:{amount}"

        # Check cache
        if cache_key in _cache:
            timestamp, cached_data = _cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                logger.info(f"ExchangeRate Cache Hit for: {cache_key}")
                return cached_data

        url = f"{self.base_url}/convert"
        params = {
            "access_key": self.api_key,
            "from": from_clean,
            "to": to_clean,
            "amount": amount
        }

        retries = 2
        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                logger.info(f"ExchangeRate API Convert Request (attempt {attempt + 1}) for: {from_clean} -> {to_clean} ({amount})")
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    
                    if not data.get("success", False):
                        error_info = data.get("error", {})
                        raise Exception(f"ExchangeRate API returned error code {error_info.get('code')}: {error_info.get('info')}")
                    
                    result_data = {
                        "from": from_clean,
                        "to": to_clean,
                        "amount": amount,
                        "quote": data.get("info", {}).get("quote", 0.0),
                        "result": data.get("result", 0.0)
                    }

                    # Cache result
                    _cache[cache_key] = (time.time(), result_data)
                    return result_data

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403):
                    logger.error(f"ExchangeRate API Authentication / Rate limit error ({status_code}): {e.response.text}")
                    raise Exception("ExchangeRate API Authentication failed.")
                if status_code >= 500 and attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"ExchangeRate API returned status code {status_code}: {e.response.text}")
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"ExchangeRate API network/timeout error: {e}")
            except Exception as e:
                raise Exception(f"Unexpected error during currency conversion: {e}")
        return {}

    def get_live_rates(self, base_curr: str = "USD", symbols: str = "") -> dict:
        """
        Retrieves live exchange rates for a base currency.
        """
        if not self.api_key:
            logger.error("ExchangeRate API key is missing. Set EXCHANGERATE_API_KEY in your .env file.")
            raise ValueError("ExchangeRate API key is not configured.")

        base_clean = base_curr.upper().strip()
        symbols_clean = symbols.upper().strip() if symbols else ""
        cache_key = f"live:{base_clean}:{symbols_clean}"

        # Check cache
        if cache_key in _cache:
            timestamp, cached_data = _cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                logger.info(f"ExchangeRate Cache Hit for: {cache_key}")
                return cached_data

        url = f"{self.base_url}/live"
        params = {
            "access_key": self.api_key,
            "source": base_clean
        }
        if symbols_clean:
            params["currencies"] = symbols_clean

        retries = 2
        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                logger.info(f"ExchangeRate API Live Request (attempt {attempt + 1}) for: {base_clean} -> {symbols_clean}")
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    
                    if not data.get("success", False):
                        error_info = data.get("error", {})
                        raise Exception(f"ExchangeRate API returned error code {error_info.get('code')}: {error_info.get('info')}")
                    
                    result_data = {
                        "base": base_clean,
                        "timestamp": data.get("timestamp", 0),
                        "rates": data.get("quotes", {})
                    }

                    # Cache result
                    _cache[cache_key] = (time.time(), result_data)
                    return result_data

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403):
                    logger.error(f"ExchangeRate API Authentication / Rate limit error ({status_code}): {e.response.text}")
                    raise Exception("ExchangeRate API Authentication failed.")
                if status_code >= 500 and attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"ExchangeRate API returned status code {status_code}: {e.response.text}")
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"ExchangeRate API network/timeout error: {e}")
            except Exception as e:
                raise Exception(f"Unexpected error during live rates lookup: {e}")
        return {}
