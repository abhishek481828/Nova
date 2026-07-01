import unittest
from unittest.mock import MagicMock, patch

from nova.browser.engine import BrowserAutomationEngine, BrowserActionException
from nova.adapters import (
    ChatGPTAdapter,
    YouTubeAdapter,
    GmailAdapter,
    GitHubAdapter,
    LinkedInAdapter,
)

class TestWebsiteAdapters(unittest.TestCase):
    
    def setUp(self):
        self.mock_engine = MagicMock(spec=BrowserAutomationEngine)
        
        # Default mock page
        self.mock_page = MagicMock()
        self.mock_page.url = "https://example.com"
        self.mock_engine.get_active_page.return_value = self.mock_page
        
    @patch("nova.adapters.chatgpt_adapter.ChatGPTAdapter.is_logged_in", return_value=True)
    @patch("nova.adapters.chatgpt_adapter.ChatGPTAdapter.handle_cookie_dialog")
    @patch("nova.adapters.chatgpt_adapter.ChatGPTAdapter.handle_onboarding_dialogs")
    def test_chatgpt_adapter_ask_question(self, mock_onboard, mock_cookie, mock_login):
        adapter = ChatGPTAdapter(self.mock_engine)
        
        mock_locator = MagicMock()
        mock_locator.first.is_visible.return_value = True
        mock_locator.first.is_editable.return_value = True
        self.mock_engine.resolve_locator.return_value = mock_locator
        
        self.mock_engine.execute_action.side_effect = [
            {"status": "success"},  # navigate
            {"status": "success"},  # wait 2s
            {"status": "success"},  # type prompt
            {"status": "success"},  # click/press send
            {"status": "success"},  # wait 1s
            {"status": "success", "text": "ChatGPT answer"}  # read_text
        ]
        
        result = adapter.ask_question("What is AI?")
        
        self.assertEqual(result, "ChatGPT answer")
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://chatgpt.com"})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "prompt textarea", "text": "What is AI?"})
        self.mock_engine.execute_action.assert_any_call("read_text", {"selector": ".markdown", "mode": "inner_text"})
        mock_cookie.assert_called_once()
        mock_onboard.assert_called_once()

    @patch("nova.adapters.chatgpt_adapter.ChatGPTAdapter.is_logged_in", return_value=False)
    @patch("nova.adapters.chatgpt_adapter.ChatGPTAdapter.handle_cookie_dialog")
    @patch("nova.adapters.chatgpt_adapter.ChatGPTAdapter.handle_onboarding_dialogs")
    def test_chatgpt_adapter_ask_question_not_logged_in(self, mock_onboard, mock_cookie, mock_login):
        adapter = ChatGPTAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        with self.assertRaises(BrowserActionException) as context:
            adapter.ask_question("What is AI?")
            
        self.assertIn("User is not logged in", str(context.exception))
        self.mock_engine.capture_diagnostics.assert_called_once()

    def test_youtube_adapter_search(self):
        adapter = YouTubeAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.search("classical music")
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://www.youtube.com"})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "input#search", "text": "classical music"})
        self.mock_engine.execute_action.assert_any_call("press_keys", {"selector": "input#search", "key": "Enter"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 2.0})

    def test_youtube_adapter_search_and_play(self):
        adapter = YouTubeAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.search_and_play("classical music")
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://www.youtube.com"})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "input#search", "text": "classical music"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "ytd-video-renderer a#video-title"})

    @patch("nova.adapters.youtube_adapter.YouTubeAdapter._get_video_paused_state", return_value=True)
    def test_youtube_adapter_play(self, mock_paused):
        adapter = YouTubeAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.play()
        
        self.mock_engine.execute_action.assert_called_once_with("press_keys", {"key": "k"})

    @patch("nova.adapters.youtube_adapter.YouTubeAdapter._get_video_paused_state", return_value=False)
    def test_youtube_adapter_pause(self, mock_paused):
        adapter = YouTubeAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.pause()
        
        self.mock_engine.execute_action.assert_called_once_with("press_keys", {"key": "k"})

    def test_youtube_adapter_toggle_play_pause(self):
        adapter = YouTubeAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.toggle_play_pause()
        
        self.mock_engine.execute_action.assert_called_once_with("press_keys", {"key": "k"})

    def test_youtube_adapter_next_previous(self):
        adapter = YouTubeAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.next()
        self.mock_engine.execute_action.assert_any_call("press_keys", {"key": "Shift+N"})
        
        adapter.previous()
        self.mock_engine.execute_action.assert_any_call("press_keys", {"key": "Shift+P"})

    def test_youtube_adapter_set_volume(self):
        adapter = YouTubeAdapter(self.mock_engine)
        
        adapter.set_volume(75)
        
        self.mock_page.locator.assert_any_call("video")
        self.mock_page.locator.return_value.first.evaluate.assert_called_once_with("(el) => { el.volume = 0.75; el.muted = false; }")

    def test_youtube_adapter_toggle_fullscreen(self):
        adapter = YouTubeAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.toggle_fullscreen()
        
        self.mock_engine.execute_action.assert_called_once_with("press_keys", {"key": "f"})

    def test_gmail_adapter_search_mail(self):
        adapter = GmailAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.search_mail("invoice")
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://mail.google.com"})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "input[placeholder='Search mail']", "text": "invoice"})
        self.mock_engine.execute_action.assert_any_call("press_keys", {"selector": "input[placeholder='Search mail']", "key": "Enter"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 2.0})

    def test_gmail_adapter_compose_email(self):
        adapter = GmailAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.compose_email("test@example.com", "Hello", "How are you?")
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://mail.google.com"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "div[role='button']:has-text('Compose')"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 1.5})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "input[peoplekit-id]", "text": "test@example.com"})
        self.mock_engine.execute_action.assert_any_call("press_keys", {"selector": "input[peoplekit-id]", "key": "Enter"})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "input[name='subjectbox']", "text": "Hello"})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "div[role='textbox'][aria-label*='Message Body']", "text": "How are you?"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "div[role='button'][aria-label*='Send']"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 1.0})

    def test_gmail_adapter_open_latest_mail(self):
        adapter = GmailAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.open_latest_mail()
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://mail.google.com"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "div[role='main'] tr[role='row']"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 2.0})

    def test_gmail_adapter_reply_to_latest_mail(self):
        adapter = GmailAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.reply_to_latest_mail("Thank you for the update!")
        
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "span[role='link']:has-text('Reply')"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 1.5})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "div[role='textbox'][aria-label*='Message Body']", "text": "Thank you for the update!"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "div[role='button'][aria-label*='Send']"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 1.0})

    def test_github_adapter_create_repository(self):
        adapter = GitHubAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.create_repository("my-project", "desc here", is_public=False)
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://github.com/new"})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "input[data-testid='repository-name-input']", "text": "my-project"})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "input[id='react-aria-2']", "text": "desc here"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "input[value='private']"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 2.0})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "button:has-text('Create repository')"})

    def test_github_adapter_open_repository(self):
        adapter = GitHubAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.open_repository("google/protobuf")
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://github.com/google/protobuf"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 2.0})

    def test_github_adapter_search_repositories(self):
        adapter = GitHubAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.search_repositories("machine learning")
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://github.com/search?q=machine%20learning&type=repositories"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 2.0})

    def test_github_adapter_search_issues(self):
        adapter = GitHubAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.search_issues("bug crash")
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://github.com/search?q=bug%20crash&type=issues"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 2.0})

    def test_github_adapter_list_pull_requests(self):
        adapter = GitHubAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        # Test specific repo
        adapter.list_pull_requests("google/protobuf")
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://github.com/google/protobuf/pulls"})
        
        # Test global
        adapter.list_pull_requests()
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://github.com/pulls"})

    def test_linkedin_adapter_send_message(self):
        adapter = LinkedInAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.send_message("John Doe", "Hey John!")
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://www.linkedin.com/messaging/"})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "input[placeholder='Search messages']", "text": "John Doe"})
        self.mock_engine.execute_action.assert_any_call("press_keys", {"selector": "input[placeholder='Search messages']", "key": "Enter"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 1.5})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "h3:has-text('John Doe')"})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "div[role='textbox'][aria-label*='Write a message']", "text": "Hey John!"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "button[type='submit']:has-text('Send')"})

    def test_linkedin_adapter_connect_with_user_direct(self):
        adapter = LinkedInAdapter(self.mock_engine)
        self.mock_engine.execute_action.return_value = {"status": "success"}
        
        adapter.connect_with_user("https://linkedin.com/in/jane", message="")
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://linkedin.com/in/jane"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "button:has-text('Connect')"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 1.0})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "button[aria-label='Send without a note']"})

    def test_linkedin_adapter_connect_with_user_more_menu(self):
        adapter = LinkedInAdapter(self.mock_engine)
        
        # click 'Connect' direct fails, click 'More' succeeds, click 'Connect' under 'More' succeeds, etc.
        self.mock_engine.execute_action.side_effect = [
            {"status": "success"},  # navigate
            {"status": "error", "message": "not found"},  # click Connect directly fails
            {"status": "success"},  # click More succeeds
            {"status": "success"},  # click Connect succeeds
            {"status": "success"},  # wait
            {"status": "success"},  # click Add a note
            {"status": "success"},  # type message note
            {"status": "success"}   # click Send now
        ]
        
        adapter.connect_with_user("https://linkedin.com/in/jane", message="Hi Jane, let's connect!")
        
        self.mock_engine.execute_action.assert_any_call("navigate", {"url": "https://linkedin.com/in/jane"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "button:has-text('Connect')"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "button:has-text('More')"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "div[role='button']:has-text('Connect')"})
        self.mock_engine.execute_action.assert_any_call("wait", {"seconds": 1.0})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "button[aria-label='Add a note']"})
        self.mock_engine.execute_action.assert_any_call("type", {"selector": "textarea[name='message']", "text": "Hi Jane, let's connect!"})
        self.mock_engine.execute_action.assert_any_call("click", {"selector": "button[aria-label='Send now']"})

if __name__ == "__main__":
    unittest.main()
