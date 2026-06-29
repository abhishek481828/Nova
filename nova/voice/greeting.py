"""
Dynamic greeting generator for Nova voice assistant.

Produces warm, conversational, time-aware greetings that vary naturally
across activations. Tracks recent history to avoid repetition.
"""
from __future__ import annotations

import random
from collections import deque
from datetime import datetime

# Track the last N greetings to avoid repetition across activations
_recent_greetings: deque[str] = deque(maxlen=5)


def _get_user_name() -> str:
    """Retrieve the user's name from the state profile, defaulting to 'Boss'."""
    try:
        from nova.state import StateManager
        StateManager.load_state()
        profile = StateManager.get_user_profile()
        if profile and isinstance(profile, dict) and profile.get("name"):
            name = profile["name"]
            # Use first name only for a natural feel
            return name.split()[0] if " " in name else name
    except Exception:
        pass
    return "Boss"


# ── Greeting pools keyed by time-of-day ──────────────────────────────────
# Each greeting is a template with {name} placeholder.
# {name} will be replaced with the user's first name, "Boss", or "Sir"
# depending on the chosen form of address for that activation.

_MORNING_GREETINGS = [
    "Good morning, {name}. I hope you're having a great start to your day.",
    "Good morning, {name}. I'm ready whenever you need me.",
    "Morning, {name}. What would you like to work on today?",
    "Good morning, {name}. Everything is ready whenever you are.",
    "Good morning, {name}. Let me know how I can help today.",
    "Morning, {name}. I hope you slept well. I'm all set.",
    "Good morning, {name}. Ready to get started whenever you are.",
    "Hello, {name}. Good morning. What can I do for you today?",
    "Morning, {name}. It's good to have you back. How can I help?",
    "Good morning, {name}. Just let me know what you'd like to do.",
]

_AFTERNOON_GREETINGS = [
    "Good afternoon, {name}. It's great to have you back.",
    "Welcome back, {name}. How can I help you today?",
    "Good afternoon, {name}. What would you like to work on?",
    "Hello, {name}. I'm ready for your next task.",
    "Good afternoon, {name}. Everything is ready whenever you are.",
    "Welcome back, {name}. What would you like to accomplish today?",
    "Afternoon, {name}. I'm here and ready whenever you need me.",
    "Hello, {name}. Good to see you again. How can I help?",
    "Good afternoon, {name}. Just let me know what you'd like to do.",
    "Welcome back, {name}. I'm all set whenever you're ready.",
]

_EVENING_GREETINGS = [
    "Good evening, {name}. I hope your day has been going well.",
    "Welcome back, {name}. What can I help you with this evening?",
    "Good evening, {name}. I'm ready whenever you are.",
    "Hello again, {name}. What would you like to do tonight?",
    "Good evening, {name}. It's great to have you back.",
    "Evening, {name}. I'm here and ready whenever you need me.",
    "Welcome back, {name}. Let's get started whenever you're ready.",
    "Good evening, {name}. What would you like to work on tonight?",
    "Hello, {name}. I hope your evening is going well. How can I help?",
    "Good evening, {name}. Just let me know what you need.",
]

_NIGHT_GREETINGS = [
    "Good evening, {name}. Working late today? I'm here whenever you need me.",
    "Welcome back, {name}. Let's get started whenever you're ready.",
    "Hello, {name}. What can I help you finish tonight?",
    "Good evening, {name}. I'm ready whenever you are.",
    "Hello, {name}. Burning the midnight oil? I'm right here with you.",
    "Welcome back, {name}. I'm all set whenever you need me.",
    "Good evening, {name}. Let me know what you'd like to work on.",
    "Hello again, {name}. I'm here to help whenever you're ready.",
    "Evening, {name}. I hope you're doing well. What can I help with?",
    "Welcome back, {name}. Just let me know how I can help tonight.",
]

# Forms of address to alternate naturally
_ADDRESS_FORMS = ["name", "Boss", "Sir"]


def get_activation_greeting() -> str:
    """
    Return a warm, conversational greeting appropriate for the current time.

    Guarantees that recent activations produce different greetings by
    tracking the last 5 greetings used.
    """
    user_name = _get_user_name()
    hour = datetime.now().hour

    if 5 <= hour < 12:
        pool = _MORNING_GREETINGS
    elif 12 <= hour < 17:
        pool = _AFTERNOON_GREETINGS
    elif 17 <= hour < 22:
        pool = _EVENING_GREETINGS
    else:
        pool = _NIGHT_GREETINGS

    # Pick a form of address, rotating naturally
    address = random.choice(_ADDRESS_FORMS)
    if address == "name":
        address = user_name

    # Format all candidates with the chosen address
    candidates = [g.format(name=address) for g in pool]

    # Remove any recently used greetings
    available = [g for g in candidates if g not in _recent_greetings]
    if not available:
        available = candidates  # fallback if pool exhausted

    greeting = random.choice(available)
    _recent_greetings.append(greeting)
    return greeting
