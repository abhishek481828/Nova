import os
import time
import httpx
from nova.logger import logger

# In-memory cache
_cache = {}
CACHE_TTL = 900  # 15 minutes

class NewsService:
    def __init__(self):
        self.api_key = os.environ.get("NEWS_API_KEY")
        self.headlines_url = "https://newsapi.org/v2/top-headlines"
        self.everything_url = "https://newsapi.org/v2/everything"

    def get_news(self, category: str = "", query: str = "", country: str = "") -> list:
        """
        Fetches breaking news or search results from NewsAPI.org.
        First attempts `/v2/top-headlines`. If no results and query is present,
        falls back to `/v2/everything`.
        """
        if not self.api_key:
            logger.error("News API key is missing. Set NEWS_API_KEY in your .env file.")
            raise ValueError("News API key is not configured.")

        # Cache key based on input parameters
        normalized_category = category.lower().strip()
        normalized_query = query.lower().strip()
        normalized_country = country.lower().strip()
        cache_key = f"{normalized_category}:{normalized_query}:{normalized_country}"

        # Check cache
        if cache_key in _cache:
            timestamp, cached_articles = _cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                logger.info(f"News Cache Hit for: {cache_key}")
                return cached_articles

        articles = self._fetch_headlines(normalized_category, normalized_query, normalized_country)
        
        # Fall back to /v2/everything if no headlines were found and query is set
        if not articles and normalized_query:
            logger.info(f"No top headlines found for query '{query}'. Falling back to /v2/everything...")
            articles = self._fetch_everything(normalized_query)

        # Store only required fields (up to 5 articles to keep LLM context clean)
        clean_articles = []
        for a in articles[:5]:
            clean_articles.append({
                "title": a.get("title", ""),
                "source": a.get("source", {}).get("name", "Unknown Source"),
                "description": a.get("description", ""),
                "url": a.get("url", "")
            })

        # Save to cache
        _cache[cache_key] = (time.time(), clean_articles)
        return clean_articles

    def _fetch_headlines(self, category: str, query: str, country: str) -> list:
        params = {"pageSize": 10}
        
        if category:
            params["category"] = category
        if query:
            params["q"] = query
        if country:
            params["country"] = country
        elif not query:
            # Default to US headlines if no query is provided
            params["country"] = "us"

        headers = {"X-Api-Key": self.api_key}

        return self._make_request(self.headlines_url, params, headers)

    def _fetch_everything(self, query: str) -> list:
        params = {
            "q": query,
            "sortBy": "publishedAt",
            "pageSize": 10
        }
        headers = {"X-Api-Key": self.api_key}

        return self._make_request(self.everything_url, params, headers)

    def _make_request(self, url: str, params: dict, headers: dict) -> list:
        retries = 2
        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                logger.info(f"News API Request (attempt {attempt + 1}) to {url.split('/')[-1]} with params {params}")
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(url, headers=headers, params=params)
                    response.raise_for_status()
                    data = response.json()
                    
                    if data.get("status") == "error":
                        raise Exception(f"News API error code {data.get('code')}: {data.get('message')}")
                        
                    return data.get("articles", [])

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403):
                    logger.error(f"News API Authentication error ({status_code}): {e.response.text}")
                    raise Exception("News API Authentication failed.")
                if status_code >= 500 and attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"News API returned status code {status_code}: {e.response.text}")
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"News API network/timeout error: {e}")
            except Exception as e:
                raise Exception(f"Unexpected error during News API lookup: {e}")
        return []
