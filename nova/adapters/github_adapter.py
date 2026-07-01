import urllib.parse
from nova.adapters.base_adapter import BaseWebsiteAdapter
from nova.browser.engine import BrowserActionException

class GitHubAdapter(BaseWebsiteAdapter):
    """Website Adapter for GitHub workflows."""
    
    def create_repository(self, repo_name: str, description: str = "", is_public: bool = True) -> None:
        """Navigates to GitHub repository creation page and creates a repository."""
        try:
            self._execute("navigate", {"url": "https://github.com/new"})
            self._execute("type", {"selector": "input[data-testid='repository-name-input']", "text": repo_name})
            
            if description:
                self._execute("type", {"selector": "input[id='react-aria-2']", "text": description})
                
            visibility = "public" if is_public else "private"
            self._execute("click", {"selector": f"input[value='{visibility}']"})
            self._execute("wait", {"seconds": 2.0})
            
            self._execute("click", {"selector": "button:has-text('Create repository')"})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"GitHub create_repository workflow failed: {e}")

    def open_repository(self, repo_path: str) -> None:
        """Opens the specified GitHub repository."""
        try:
            target_url = f"https://github.com/{repo_path.strip('/')}"
            self._execute("navigate", {"url": target_url})
            self._execute("wait", {"seconds": 2.0})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"GitHub open_repository workflow failed: {e}")

    def search_repositories(self, query: str) -> None:
        """Searches GitHub for repositories matching the query."""
        try:
            encoded_query = urllib.parse.quote(query)
            target_url = f"https://github.com/search?q={encoded_query}&type=repositories"
            self._execute("navigate", {"url": target_url})
            self._execute("wait", {"seconds": 2.0})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"GitHub search_repositories workflow failed: {e}")

    def search_issues(self, query: str) -> None:
        """Searches GitHub for issues matching the query."""
        try:
            encoded_query = urllib.parse.quote(query)
            target_url = f"https://github.com/search?q={encoded_query}&type=issues"
            self._execute("navigate", {"url": target_url})
            self._execute("wait", {"seconds": 2.0})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"GitHub search_issues workflow failed: {e}")

    def list_pull_requests(self, repo_path: str = "") -> None:
        """Lists pull requests globally or for a specific repository."""
        try:
            if repo_path:
                target_url = f"https://github.com/{repo_path.strip('/')}/pulls"
            else:
                target_url = "https://github.com/pulls"
            self._execute("navigate", {"url": target_url})
            self._execute("wait", {"seconds": 2.0})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"GitHub list_pull_requests workflow failed: {e}")
