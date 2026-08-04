"""Conversational Execution Context with Pronoun Resolution."""

import time
from typing import Optional


class ExecutionContext:
    def __init__(self, ttl_ms: int = 60000):
        self.ttl_ms = ttl_ms
        self.last_contact: Optional[str] = None
        self.last_app: Optional[str] = None
        self.last_timestamp: float = 0.0

    def update_context(self, contact: Optional[str] = None, app: Optional[str] = None):
        if contact:
            self.last_contact = contact
        if app:
            self.last_app = app
        self.last_timestamp = time.time()

    def resolve_contact(self, pronoun_or_name: str) -> str:
        clean = pronoun_or_name.strip().lower()
        if clean in ("him", "her", "them", "he", "she") and self.is_context_valid():
            return self.last_contact or pronoun_or_name
        return pronoun_or_name

    def is_context_valid(self) -> bool:
        return (time.time() - self.last_timestamp) * 1000 <= self.ttl_ms

    def clear(self):
        self.last_contact = None
        self.last_app = None
        self.last_timestamp = 0.0
