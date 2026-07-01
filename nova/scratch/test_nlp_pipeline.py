import unittest
from nova.nlp_pipeline import NlpPipeline

class TestNlpPipeline(unittest.TestCase):
    def setUp(self):
        self.pipeline = NlpPipeline(debug_mode=False)

    def test_correct_sentences_untouched(self):
        # Already correct sentences should not change
        text = "What do you know about me?"
        res = self.pipeline.process(text)
        self.assertEqual(res["corrected"], "What do you know about me?")
        self.assertEqual(len(res["corrections"]), 0)

        # "currently" should not be touched
        text = "I am currently working on this task."
        res = self.pipeline.process(text)
        self.assertEqual(res["corrected"], "I am currently working on this task.")

    def test_spelling_corrections(self):
        # Typo: Opne -> Open
        text = "Opne Chrome"
        res = self.pipeline.process(text)
        self.assertEqual(res["corrected"], "Open Chrome")
        self.assertEqual(len(res["corrections"]), 1)
        self.assertEqual(res["corrections"][0]["original"], "Opne")
        self.assertEqual(res["corrections"][0]["corrected"], "Open")

    def test_protected_technical_terms(self):
        # Protected vocabulary should not change
        terms = ["Nova", "Chromium", "NixOS", "Ollama", "Playwright", "ChatGPT", "GitHub", "Python", "JavaScript", "VS Code", "SQLite"]
        for term in terms:
            res = self.pipeline.process(f"Using {term} now")
            self.assertIn(term, res["corrected"])

    def test_protected_urls_and_emails(self):
        # URLs should be untouched
        text = "Go to https://github.com/abhishek481828/Nova"
        res = self.pipeline.process(text)
        self.assertEqual(res["corrected"], "Go to https://github.com/abhishek481828/Nova")

        # Emails should be untouched
        text = "Email test@example.com please"
        res = self.pipeline.process(text)
        self.assertEqual(res["corrected"], "Email test@example.com please")

    def test_protected_file_paths(self):
        # File paths should be untouched
        paths = ["/home/nixos/file.txt", "./nova/spelling.py", "config.json"]
        for path in paths:
            res = self.pipeline.process(f"Read path {path} now")
            self.assertIn(path, res["corrected"])

    def test_shell_commands_and_options(self):
        # Shell commands and options should be untouched
        text = "Run sudo systemctl restart ollama --force -v"
        res = self.pipeline.process(text)
        self.assertEqual(res["corrected"], "Run sudo systemctl restart ollama --force -v")

    def test_code_snippets(self):
        # Code snippets should be untouched
        text = "Execute import sys; print(sys.path) function"
        res = self.pipeline.process(text)
        self.assertIn("import sys", res["corrected"])
        self.assertIn("print(sys.path)", res["corrected"])

    def test_capitalization_and_punctuation(self):
        # Punctuation and mixed casing should be preserved
        text = "HELLOO, chrome is greaat!"
        res = self.pipeline.process(text)
        self.assertEqual(res["corrected"], "HELLO, chrome is great!")

    def test_low_confidence_threshold_skips(self):
        # A totally weird gibberish word with low similarity should not be guessed
        text = "open xyzabcqwe"
        res = self.pipeline.process(text)
        self.assertEqual(res["corrected"], "open xyzabcqwe")
        self.assertIn("xyzabcqwe", res["skipped"][0] if res["skipped"] else [])

if __name__ == "__main__":
    unittest.main()
