import os
import time
import httpx
from nova.logger import logger
from nova.config import GITHUB_API_KEY

# In-memory cache
_cache = {}
CACHE_TTL = 60  # 1 minute

class GitHubService:
    def __init__(self):
        self.api_key = GITHUB_API_KEY
        self.base_url = "https://api.github.com"

    def get_profile(self) -> dict:
        """Fetches the authenticated user's profile details."""
        return self._make_request("/user")

    def get_notifications(self) -> list:
        """Fetches recent notifications for the authenticated user."""
        raw_notifs = self._make_request("/notifications?per_page=10")
        
        # Clean notifications
        clean_notifs = []
        for n in raw_notifs[:5]:
            clean_notifs.append({
                "title": n.get("subject", {}).get("title", "No Title"),
                "repo": n.get("repository", {}).get("full_name", "Unknown Repo"),
                "reason": n.get("reason", "mention"),
                "type": n.get("subject", {}).get("type", "Issue")
            })
        return clean_notifs

    def list_repos(self) -> list:
        """Lists recent repositories for the authenticated user, sorted by update time."""
        raw_repos = self._make_request("/user/repos?sort=updated&per_page=10")
        
        # Clean repository details
        clean_repos = []
        for r in raw_repos[:5]:
            clean_repos.append({
                "name": r.get("name", ""),
                "full_name": r.get("full_name", ""),
                "description": r.get("description", "") or "No description",
                "stars": r.get("stargazers_count", 0),
                "url": r.get("html_url", "")
            })
        return clean_repos

    def list_issues(self) -> list:
        """Lists recent open issues assigned or created by the user."""
        raw_issues = self._make_request("/issues?state=open&sort=updated&per_page=10")
        
        # Clean issue details
        clean_issues = []
        for i in raw_issues[:5]:
            clean_issues.append({
                "title": i.get("title", ""),
                "repo": i.get("repository", {}).get("full_name", "Unknown Repo"),
                "state": i.get("state", "open"),
                "url": i.get("html_url", ""),
                "number": i.get("number", 0)
            })
        return clean_issues

    def _make_request(self, endpoint: str) -> any:
        if not self.api_key:
            logger.error("GitHub API key is missing. Set GITHUB_API_KEY in your .env file.")
            raise ValueError("GitHub API key is not configured.")

        # Check cache
        cache_key = endpoint
        if cache_key in _cache:
            timestamp, cached_data = _cache[cache_key]
            if time.time() - timestamp < CACHE_TTL:
                logger.info(f"GitHub Cache Hit for: {cache_key}")
                return cached_data

        url = f"{self.base_url}{endpoint}"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.api_key}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "Nova-AI-Assistant"
        }

        retries = 2
        backoff = 1.0
        for attempt in range(retries + 1):
            try:
                logger.info(f"GitHub API Request (attempt {attempt + 1}) to: {endpoint}")
                with httpx.Client(timeout=10.0) as client:
                    response = client.get(url, headers=headers)
                    response.raise_for_status()
                    data = response.json()
                    
                    # Save to cache
                    _cache[cache_key] = (time.time(), data)
                    return data

            except httpx.HTTPStatusError as e:
                status_code = e.response.status_code
                if status_code in (401, 403):
                    logger.error(f"GitHub API Authentication / Scope / Rate limit error ({status_code}): {e.response.text}")
                    if status_code == 403:
                        raise Exception("GitHub API returned 403 Forbidden. Your token might be missing permissions for this specific endpoint (e.g. notifications, user scope).")
                    raise Exception(f"GitHub API Authentication failed ({status_code}).")
                if status_code >= 500 and attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"GitHub API returned status code {status_code}: {e.response.text}")
            except (httpx.TimeoutException, httpx.ConnectError) as e:
                if attempt < retries:
                    time.sleep(backoff)
                    backoff *= 2.0
                    continue
                raise Exception(f"GitHub API network/timeout error: {e}")
            except Exception as e:
                raise Exception(f"Unexpected error during GitHub API request: {e}")
        return []
