import os
import time
import httpx
from nova.logger import logger
from nova.config import TMDB_API_KEY

# In-memory cache
_cache = {}
CACHE_TTL = 43200  # 12 hours (movie metadata and trending lists change slowly)

class TmdbService:
    def __init__(self):
        self.api_key = TMDB_API_KEY
        self.base_url = "https://api.tmdb.org/3"

    def _query(self, endpoint: str, params: dict = None) -> dict:
        if not self.api_key:
            logger.error("TMDB API key is missing. Set TMDB_API_KEY in your .env file.")
            raise ValueError("TMDB API key is not configured.")

        if params is None:
            params = {}
        
        # Inject API key query param
        params["api_key"] = self.api_key
        
        # Simple cache key matching endpoint + string params
        param_str = "&".join(f"{k}={v}" for k, v in sorted(params.items()) if k != "api_key")
        cache_key = f"{endpoint}:{param_str}"

        # Check cache
        if cache_key in _cache:
            timestamp, cached_data = _cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                logger.info(f"TMDB Cache Hit for: {cache_key}")
                return cached_data

        url = f"{self.base_url}{endpoint}"
        retries = 2
        backoff = 1.0
        
        for attempt in range(retries + 1):
            try:
                logger.info(f"TMDB API Request (attempt {attempt + 1}) for endpoint {endpoint}")
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(url, params=params)
                    response.raise_for_status()
                    data = response.json()
                    
                    # Cache result
                    _cache[cache_key] = (time.time(), data)
                    return data

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403):
                    logger.error(f"TMDB API Authentication / Rate limit error ({status_code}): {e.response.text}")
                    raise Exception("TMDB API Authentication failed.")
                if status_code >= 500 and attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"TMDB API returned status code {status_code}: {e.response.text}")
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"TMDB API network/timeout error: {e}")
            except Exception as e:
                raise Exception(f"Unexpected error during TMDB lookup: {e}")
        return {}

    def search_movie(self, query: str) -> dict:
        """Searches for a movie by title."""
        return self._query("/search/movie", {"query": query, "include_adult": "false"})

    def search_tv(self, query: str) -> dict:
        """Searches for a TV show by title."""
        return self._query("/search/tv", {"query": query, "include_adult": "false"})

    def get_trending_movies(self) -> dict:
        """Retrieves today's trending movies."""
        return self._query("/trending/movie/day")

    def get_trending_tv(self) -> dict:
        """Retrieves today's trending TV shows."""
        return self._query("/trending/tv/day")
