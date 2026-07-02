import os
import time
import httpx
from nova.logger import logger
from nova.config import COINGECKO_API_KEY

# In-memory cache
_cache = {}
CACHE_TTL = 60  # 1 minute

class CoinGeckoService:
    def __init__(self):
        self.api_key = COINGECKO_API_KEY
        self.base_url = "https://api.coingecko.com/api/v3/simple/price"

    def get_price(self, coin_id: str, vs_currency: str = "usd") -> float:
        """
        Queries CoinGecko for the price of a coin.
        Returns the price as a float.
        """
        if not self.api_key:
            logger.error("CoinGecko API key is missing. Set COINGECKO_API_KEY in your .env file.")
            raise ValueError("CoinGecko API key is not configured.")

        coin_clean = coin_id.lower().strip()
        currency_clean = vs_currency.lower().strip()
        cache_key = f"{coin_clean}:{currency_clean}"

        # Check cache
        if cache_key in _cache:
            timestamp, price = _cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                logger.info(f"CoinGecko Cache Hit for: {cache_key}")
                return price

        params = {
            "ids": coin_clean,
            "vs_currencies": currency_clean
        }

        headers = {
            "x-cg-demo-api-key": self.api_key
        }

        retries = 2
        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                logger.info(f"CoinGecko API Request (attempt {attempt + 1}) for: {coin_clean} ({currency_clean})")
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(self.base_url, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()
                    
                    price = float(data.get(coin_clean, {}).get(currency_clean, 0.0))
                    if price == 0.0:
                        # Sometimes CoinGecko doesn't fail but returns empty JSON if coin_id is wrong
                        raise ValueError(f"No price data found for coin '{coin_id}' in currency '{vs_currency}'.")

                    # Cache the result
                    _cache[cache_key] = (time.time(), price)
                    return price

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403):
                    logger.error(f"CoinGecko API Authentication error ({status_code}): {e.response.text}")
                    raise Exception("CoinGecko API Authentication failed.")
                if status_code >= 500 and attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"CoinGecko API returned status code {status_code}: {e.response.text}")
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"CoinGecko API network/timeout error: {e}")
            except Exception as e:
                raise Exception(f"Unexpected error during CoinGecko price lookup: {e}")
