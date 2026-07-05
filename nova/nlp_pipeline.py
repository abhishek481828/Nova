import re
import json
import logging
from typing import Dict, Any, List, Optional, Set, Tuple
from spellchecker import SpellChecker
from nova.config import APPS_JSON_PATH
from nova.utils import print_info

# Configure logging for corrections
nlp_logger = logging.getLogger("nova.nlp")

# Default protected words list
DEFAULT_PROTECTED_WORDS = {
    "nova", "chromium", "nixos", "ollama", "playwright", "chatgpt", "github", 
    "python", "javascript", "vscode", "sqlite", "vs code", "chrome", "firefox",
    "scrcpy", "tailscale", "vlc", "systemctl", "journalctl", "systemd",
    "warp-cli", "warp", "nix-env", "nixpkgs", "nix-shell", "pandas", "numpy",
    "webrtcvad", "neofetch", "sudo", "sys", "import", "print", "path", "git",
    "apps", "applications"
}

# Common bigrams in Nova to boost confidence score (context-awareness)
COMMON_BIGRAMS = {
    ("open", "chrome"), ("open", "chromium"), ("open", "firefox"), ("open", "youtube"), 
    ("open", "terminal"), ("open", "browser"), ("open", "app"), ("open", "vscode"),
    ("run", "command"), ("run", "script"), ("run", "app"),
    ("set", "volume"), ("set", "brightness"),
    ("git", "status"), ("git", "commit"), ("git", "push"), ("git", "pull"),
    ("show", "dashboard"), ("show", "specs"),
    ("suspend", "system"), ("shutdown", "system"),
    ("check", "status"), ("check", "connections"), ("diagnose", "connections")
}

def edit_distance(s1: str, s2: str) -> int:
    if len(s1) < len(s2):
        return edit_distance(s2, s1)
    if len(s2) == 0:
        return len(s1)
    
    previous_row = list(range(len(s2) + 1))
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row
        
    return previous_row[-1]

class NlpPipeline:
    def __init__(
        self,
        spell_checker: Optional[SpellChecker] = None,
        confidence_threshold: float = 0.75,
        debug_mode: bool = True
    ) -> None:
        self.spell = spell_checker or SpellChecker()
        self.confidence_threshold = confidence_threshold
        self.debug_mode = debug_mode
        self.protected_vocab: Set[str] = set(DEFAULT_PROTECTED_WORDS)
        self._load_apps_vocab()
        
        # Load valid words from vocabulary module
        from nova.vocabulary import VALID_WORDS
        self.protected_vocab.update(VALID_WORDS)
            
        # Load protected vocabulary directly into the spell checker so it doesn't try to correct them
        # Set high frequency to prioritize domain-specific terminology during correction
        for word in self.protected_vocab:
            self.spell.word_frequency.dictionary[word.lower()] = 100000

    def _load_apps_vocab(self) -> None:
        """Loads application names/aliases dynamically from apps.json."""
        if APPS_JSON_PATH.exists():
            try:
                with open(APPS_JSON_PATH, "r", encoding="utf-8") as f:
                    apps_map = json.load(f)
                    for key in apps_map.keys():
                        self.protected_vocab.add(key.lower())
                        for part in key.lower().split():
                            self.protected_vocab.add(part)
            except Exception as e:
                nlp_logger.error(f"Error loading apps vocabulary from {APPS_JSON_PATH}: {e}")

    def add_protected_word(self, word: str) -> None:
        """Adds a word to the customizable protected vocabulary."""
        word_clean = word.strip().lower()
        if word_clean:
            self.protected_vocab.add(word_clean)
            self.spell.word_frequency.dictionary[word_clean] = 100000

    def normalize(self, text: str) -> str:
        """
        Performs text normalization.
        Cleans prompt prefixes, spaces, quotes, and punctuation formatting.
        """
        if not text:
            return ""
        
        # Clean leading prompt symbols "nova ❯", "nova:", "nova", prompt indicators "❯", ">", ":"
        normalized = text
        while True:
            prev = normalized
            normalized = re.sub(r'^(nova\b|❯|>|:|\s)+', '', normalized, flags=re.IGNORECASE).strip()
            if normalized == prev:
                break
                
        # Clean multiple spaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        return normalized

    def detect_protected_elements(self, text: str) -> Tuple[str, Dict[str, str]]:
        """
        Identifies URLs, file paths, commands, code snippets, package names, 
        and emails. Replaces them with placeholder strings to keep them 
        completely untouched by spellcheck.
        """
        placeholders: Dict[str, str] = {}
        counter = 0

        # Helper to generate and map placeholders
        def make_placeholder(match: re.Match) -> str:
            nonlocal counter
            val = match.group(0)
            placeholder = f"__PROTECTED_{counter}__"
            placeholders[placeholder] = val
            counter += 1
            return placeholder

        # 1. URL detection
        url_regex = re.compile(r'\bhttps?://\S+|www\.\S+\b', re.IGNORECASE)
        text = url_regex.sub(make_placeholder, text)

        # 2. Email detection
        email_regex = re.compile(r'\b[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}\b')
        text = email_regex.sub(make_placeholder, text)

        # 3. File path / path-like detection
        path_regex = re.compile(r'\b/(?:[\w.-]+/)*[\w.-]+\b|[\w.-]+\.(?:py|json|sh|txt|nix|csv|md)\b')
        text = path_regex.sub(make_placeholder, text)

        # 4. Command line arguments / options (e.g. -la, --version)
        cmd_opt_regex = re.compile(r'\b--\w+|-\w+\b')
        text = cmd_opt_regex.sub(make_placeholder, text)

        # 5. Code snippets (e.g. function calls, assignments, keywords)
        code_regex = re.compile(r'\w+\(\)|\w+=\w+|\bdef\b|\bimport\b')
        text = code_regex.sub(make_placeholder, text)

        # 6. Specific protected words (case-insensitive boundary checks)
        sorted_protected = sorted(list(self.protected_vocab), key=len, reverse=True)
        for word in sorted_protected:
            if not word:
                continue
            word_regex = re.compile(rf'\b{re.escape(word)}\b', re.IGNORECASE)
            text = word_regex.sub(make_placeholder, text)

        return text, placeholders

    def calculate_confidence(self, original: str, candidate: str, preceding: Optional[str] = None, following: Optional[str] = None) -> float:
        """
        Computes the confidence score of a typo correction candidate.
        Considers edit distance, length ratios, and common bigrams context.
        """
        orig_lower = original.lower()
        cand_lower = candidate.lower()
        
        # Levenshtein distance calculations
        distance = edit_distance(orig_lower, cand_lower)
        max_len = max(len(orig_lower), len(cand_lower))
        similarity = 1.0 - (distance / max_len) if max_len > 0 else 1.0
        
        # Context-awareness check:
        # Boost confidence if candidate forms a common bigram with preceding or following word
        boost = 0.0
        if preceding:
            if (preceding.lower(), cand_lower) in COMMON_BIGRAMS:
                boost += 0.15
        if following:
            if (cand_lower, following.lower()) in COMMON_BIGRAMS:
                boost += 0.15
                
        confidence = min(1.0, similarity + boost)
        return confidence

    def correct_typos(self, text: str, placeholders: Dict[str, str]) -> Tuple[str, List[Dict[str, Any]], List[str]]:
        """
        Performs typo correction on unprotected tokens.
        Preserves original capitalization, punctuation, and returns logs.
        """
        corrections_applied = []
        skipped_corrections = []

        # Split text into tokens keeping spaces and punctuation intact
        tokens = re.split(r'(\b[a-zA-Z]{3,}\b)', text)
        
        corrected_tokens = []
        for i, token in enumerate(tokens):
            if re.match(r'^[a-zA-Z]{3,}$', token):
                token_lower = token.lower()
                
                # Check if this is a placeholder or a protected word
                if token in placeholders or token_lower in self.protected_vocab:
                    corrected_tokens.append(token)
                    continue
                    
                # If it's already a valid dictionary word, NEVER modify it!
                if token_lower in self.spell:
                    corrected_tokens.append(token)
                    continue
                    
                # Check closest correction candidate
                candidate = self.spell.correction(token)
                
                # Context-aware override for 'open' typos
                preceding = None
                following = None
                
                for j in range(i - 1, -1, -1):
                    cleaned_t = tokens[j].strip()
                    if re.match(r'^[a-zA-Z]{3,}$', cleaned_t) or cleaned_t in placeholders:
                        preceding = placeholders.get(cleaned_t, cleaned_t)
                        break
                        
                for j in range(i + 1, len(tokens)):
                    cleaned_t = tokens[j].strip()
                    if re.match(r'^[a-zA-Z]{3,}$', cleaned_t) or cleaned_t in placeholders:
                        following = placeholders.get(cleaned_t, cleaned_t)
                        break
                
                # Typo override context check
                override_confidence = None
                if token_lower in ("opne", "ope", "opn", "oppen") and following and following.lower() in ("chrome", "chromium", "firefox", "browser", "tab", "youtube", "terminal", "vlc", "scrcpy"):
                    candidate = "open"
                    override_confidence = 1.0
                
                if candidate and candidate.lower() != token_lower:
                    confidence = override_confidence if override_confidence is not None else self.calculate_confidence(token, candidate, preceding, following)
                    
                    if confidence >= self.confidence_threshold:
                        replacement = candidate
                        if token.istitle():
                            replacement = candidate.capitalize()
                        elif token.isupper():
                            replacement = candidate.upper()
                            
                        corrected_tokens.append(replacement)
                        
                        corrections_applied.append({
                            "original": token,
                            "corrected": replacement,
                            "confidence": round(confidence, 2)
                        })
                        
                        nlp_logger.info(f"NLP Correction: '{token}' -> '{replacement}' (Confidence: {confidence:.2f})")
                        continue
                    else:
                        skipped_corrections.append(f"{token} -> {candidate} (Confidence: {confidence:.2f} < {self.confidence_threshold})")
                        nlp_logger.info(f"NLP Correction Skipped: '{token}' -> '{candidate}' (Low Confidence: {confidence:.2f})")
                else:
                    # No candidates found
                    skipped_corrections.append(f"{token} -> [No candidates]")
                        
                corrected_tokens.append(token)
            else:
                corrected_tokens.append(token)
                
        corrected_text = "".join(corrected_tokens)
        return corrected_text, corrections_applied, skipped_corrections

    def restore_placeholders(self, text: str, placeholders: Dict[str, str]) -> str:
        """Restores original protected elements back in place of tags."""
        restored = text
        for placeholder, original_val in placeholders.items():
            restored = restored.replace(placeholder, original_val)
        return restored

    def process(self, text: str) -> Dict[str, Any]:
        """
        Executes the entire NLP Preprocessing pipeline.
        Normalization -> Protected Word Detection -> Typo Correction -> Tokenization.
        """
        if not text:
            return {
                "original": "",
                "normalized": "",
                "corrected": "",
                "corrections": [],
                "skipped": [],
                "protected_words": list(self.protected_vocab)
            }

        # Step 1: Normalization
        normalized = self.normalize(text)

        # Step 2: Protected Word Detection
        protected_text, placeholders = self.detect_protected_elements(normalized)

        # Step 3: Confidence-Based Typo Correction
        corrected_text, corrections, skipped = self.correct_typos(protected_text, placeholders)

        # Step 4: Restore protected elements
        final_text = self.restore_placeholders(corrected_text, placeholders)

        # Log summary
        if corrections:
            nlp_logger.info(f"Original Input: '{text}'")
            nlp_logger.info("Corrections Applied:")
            for c in corrections:
                nlp_logger.info(f"  {c['original']} -> {c['corrected']} (Confidence: {c['confidence']})")
        else:
            nlp_logger.info(f"Original Input: '{text}'")
            nlp_logger.info("Corrections Applied: None")

        # Step 5: Tokenization
        tokens = [t for t in re.findall(r'\b\w+\b', final_text) if t]

        result = {
            "original": text,
            "normalized": normalized,
            "corrected": final_text,
            "tokens": tokens,
            "corrections": corrections,
            "skipped": skipped,
            "protected_words": sorted(list(self.protected_vocab))
        }

        if self.debug_mode:
            print_debug_info(result)

        return result

def print_debug_info(res: Dict[str, Any]) -> None:
    """Helper to display nlp pipeline internals in debug console."""
    print_info("--- NLP Pipeline Debug ---")
    print_info(f"Original Text: '{res['original']}'")
    print_info(f"Normalized Text: '{res['normalized']}'")
    print_info(f"Corrected Text: '{res['corrected']}'")
    print_info(f"Tokens: {res['tokens']}")
    print_info(f"Corrections: {res['corrections']}")
    print_info(f"Skipped Corrections: {res['skipped']}")
    print_info(f"Protected words count: {len(res['protected_words'])}")
    print_info("--------------------------")
