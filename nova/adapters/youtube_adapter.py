from nova.adapters.base_adapter import BaseWebsiteAdapter
from nova.browser.engine import BrowserActionException

class YouTubeAdapter(BaseWebsiteAdapter):
    """Website Adapter for YouTube workflows."""
    
    def search(self, query: str) -> None:
        """Searches YouTube for the specified query."""
        try:
            page = self.engine.get_active_page(silent=True)
            if "youtube.com" not in page.url:
                self._execute("navigate", {"url": "https://www.youtube.com"})
                
            self._execute("type", {"selector": "input#search", "text": query})
            self._execute("press_keys", {"selector": "input#search", "key": "Enter"})
            self._execute("wait", {"seconds": 2.0})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"YouTube search workflow failed: {e}")

    def search_and_play(self, query: str) -> None:
        """Searches YouTube and plays the first matching video."""
        try:
            self.search(query)
            self._execute("click", {"selector": "ytd-video-renderer a#video-title"})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"YouTube search_and_play workflow failed: {e}")

    def _get_video_paused_state(self) -> bool:
        """Helper to check if the video element is currently paused."""
        try:
            page = self.engine.get_active_page(silent=True)
            is_paused = page.locator("video").first.evaluate("(el) => el.paused")
            return bool(is_paused)
        except Exception:
            return True

    def play(self) -> None:
        """Resumes video playback if paused."""
        try:
            if self._get_video_paused_state():
                self._execute("press_keys", {"key": "k"})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"YouTube play action failed: {e}")

    def pause(self) -> None:
        """Pauses video playback if active."""
        try:
            if not self._get_video_paused_state():
                self._execute("press_keys", {"key": "k"})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"YouTube pause action failed: {e}")

    def toggle_play_pause(self) -> None:
        """Toggles the play/pause state of the video player."""
        try:
            self._execute("press_keys", {"key": "k"})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"YouTube toggle play/pause failed: {e}")

    def next(self) -> None:
        """Skips to the next video in the playlist or queue."""
        try:
            self._execute("press_keys", {"key": "Shift+N"})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"YouTube next video failed: {e}")

    def previous(self) -> None:
        """Returns to the previous video."""
        try:
            self._execute("press_keys", {"key": "Shift+P"})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"YouTube previous video failed: {e}")

    def set_volume(self, volume: int) -> None:
        """Sets the volume coefficient (0-100) directly on the HTML5 video element."""
        if not (0 <= volume <= 100):
            raise BrowserActionException("Volume must be an integer between 0 and 100.")
        try:
            page = self.engine.get_active_page(silent=True)
            page.locator("video").first.evaluate(f"(el) => {{ el.volume = {volume / 100.0}; el.muted = false; }}")
        except Exception as e:
            self.engine.capture_diagnostics(e)
            raise BrowserActionException(f"YouTube set volume action failed: {e}")

    def toggle_fullscreen(self) -> None:
        """Toggles fullscreen mode on the video player."""
        try:
            self._execute("press_keys", {"key": "f"})
        except Exception as e:
            self.engine.capture_diagnostics(e)
            if isinstance(e, BrowserActionException):
                raise
            raise BrowserActionException(f"YouTube toggle fullscreen failed: {e}")
