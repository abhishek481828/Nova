"""
nova.session.intent_resolver
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
Lightweight keyword/pattern-based resolver that maps a user's natural-language
follow-up phrase to a FollowupIntent without calling an LLM.

Resolution is intentionally conservative: any phrase that does NOT clearly
match a follow-up pattern is returned as FollowupIntent.NONE so it falls
through to the normal planner pipeline.
"""
from __future__ import annotations

import re
from typing import List, Tuple

from nova.session.models import FollowupIntent


# ── Pattern table ─────────────────────────────────────────────────────────────
# Each entry is (intent, [regex_patterns]).
# Patterns are matched case-insensitively against the stripped user text.
# First match wins.

_PATTERNS: List[Tuple[FollowupIntent, List[str]]] = [
    (
        FollowupIntent.UNDO,
        [
            r"^undo(\s+(that|last|it|the last( change| edit| task)?))?$",
            r"^revert(\s+(that|last|it))?$",
            r"^go back$",
            r"^take that back$",
            r"^roll(back| it back)$",
        ],
    ),
    (
        FollowupIntent.REDO,
        [
            r"^redo(\s+(that|it|last))?$",
            r"^redo the last( change| edit| task)?$",
        ],
    ),
    (
        FollowupIntent.CONTINUE,
        [
            r"^continue(\s+(please|that|it|going)?)?$",
            r"^keep going(\s+please)?$",
            r"^go on(\s+please)?$",
            r"^proceed(\s+please)?$",
            r"^next(\s+step)?$",
            r"^carry on(\s+please)?$",
            r"^finish(\s+(it|that|up))?$",
        ],
    ),
    (
        FollowupIntent.EXPLAIN,
        [
            r"^explain(\s+(that|it|this|again|what you did|the code|the change))?$",
            r"^what did you (do|create|change|generate)\??$",
            r"^what('s| is) that\??$",
            r"^how does (it|this|that) work\??$",
            r"^walk me through (it|that|this)$",
            r"^describe (it|that|this|the change)$",
        ],
    ),
    (
        FollowupIntent.IMPROVE,
        [
            r"^improve(\s+(it|that|this|the code))?$",
            r"^make it better(\s+please)?$",
            r"^enhance(\s+(it|that|this))?$",
            r"^improve the (code|implementation|solution)$",
            r"^can you improve (it|that)\??$",
        ],
    ),
    (
        FollowupIntent.REFACTOR,
        [
            r"^refactor(\s+(it|that|this|the code))?$",
            r"^clean (it|that) up(\s+please)?$",
            r"^clean up (the code|this)$",
            r"^restructure(\s+(it|that|the code))?$",
            r"^reorganize(\s+(it|that|the code))?$",
        ],
    ),
    (
        FollowupIntent.ADD_TESTS,
        [
            r"^add tests?(\s+(for it|please|now))?$",
            r"^write tests?(\s+(for it|please|now))?$",
            r"^generate tests?(\s+(for it|please|now))?$",
            r"^add unit tests?$",
            r"^write unit tests?$",
            r"^create tests?$",
            r"^test it(\s+please)?$",
        ],
    ),
    (
        FollowupIntent.OPTIMIZE,
        [
            r"^optimize(\s+(it|that|this|the code))?$",
            r"^make it faster(\s+please)?$",
            r"^improve (the )?performance(\s+please)?$",
            r"^speed it up(\s+please)?$",
            r"^make it more efficient(\s+please)?$",
        ],
    ),
    (
        FollowupIntent.DOCUMENT,
        [
            r"^document(\s+(it|that|this|the code))?$",
            r"^add docs?(\s+(please|to it|to that))?$",
            r"^add docstrings?(\s+(please|to it|to that))?$",
            r"^write (the )?docs?$",
            r"^generate (the )?docs?$",
            r"^add comments?(\s+(please|to it|to that))?$",
            r"^document the code(\s+please)?$",
        ],
    ),
]

# Pre-compile all patterns
_COMPILED: List[Tuple[FollowupIntent, List[re.Pattern]]] = [
    (intent, [re.compile(p, re.IGNORECASE) for p in patterns])
    for intent, patterns in _PATTERNS
]


def resolve_intent(user_text: str) -> FollowupIntent:
    """
    Resolve a user's natural-language phrase to a FollowupIntent.

    Parameters
    ----------
    user_text : str
        The raw user input (voice transcript or CLI text).

    Returns
    -------
    FollowupIntent
        The matched intent, or ``FollowupIntent.NONE`` if no match found.
    """
    text = user_text.strip().rstrip(".!?")
    if not text:
        return FollowupIntent.NONE

    for intent, compiled_patterns in _COMPILED:
        for pattern in compiled_patterns:
            if pattern.match(text):
                return intent

    return FollowupIntent.NONE


def is_followup(user_text: str) -> bool:
    """Return True if the text resolves to any follow-up intent (not NONE)."""
    return resolve_intent(user_text) != FollowupIntent.NONE
