import os
import time
import httpx
from nova.logger import logger

# Simple in-memory cache
_cache = {}
CACHE_TTL = 300  # 5 minutes

class TavilyService:
    def __init__(self):
        self.api_key = os.environ.get("TAVILY_API_KEY")
        self.base_url = "https://api.tavily.com/search"

    def search(self, query: str) -> list:
        """
        Performs a search on Tavily and returns a list of results.
        Each result has 'title', 'url', and 'content'.
        """
        if not self.api_key:
            logger.error("Tavily API key is missing. Set TAVILY_API_KEY in your .env file.")
            raise ValueError("Tavily API key is not configured.")

        normalized_query = query.lower().strip()
        
        # Check cache
        if normalized_query in _cache:
            timestamp, cached_results = _cache[normalized_query]
            if time.time() - timestamp < CACHE_TTL:
                logger.info(f"Tavily Cache Hit for query: {query}")
                return cached_results

        payload = {
            "api_key": self.api_key,
            "query": query,
            "search_depth": "basic",
            "max_results": 5
        }

        retries = 2
        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                logger.info(f"Tavily API Request (attempt {attempt + 1}) for query: {query}")
                with httpx.Client(timeout=10.0) as client:
                    response = client.post(self.base_url, json=payload)
                    response.raise_for_status()
                    data = response.json()
                    results = data.get("results", [])
                    
                    # Store only required fields to keep it clean
                    clean_results = []
                    for r in results:
                        clean_results.append({
                            "title": r.get("title", ""),
                            "url": r.get("url", ""),
                            "content": r.get("content", "")
                        })
                        
                    # Save in cache
                    _cache[normalized_query] = (time.time(), clean_results)
                    return clean_results
                    
            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403):
                    logger.error(f"Tavily API Authentication error ({status_code}): {e.response.text}")
                    raise Exception("Tavily API Authentication failed.")
                if status_code >= 500 and attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"Tavily API returned status code {status_code}: {e.response.text}")
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"Tavily API network/timeout error: {e}")
            except Exception as e:
                raise Exception(f"Unexpected error during Tavily search: {e}")
