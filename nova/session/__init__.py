"""
nova.session
~~~~~~~~~~~~
Development Session Manager — Public API.

Gives Nova persistent memory of the current software development session,
enabling follow-up understanding, undo/redo, and AI context injection.

Quick start
-----------
    from nova.session import get_dev_session_manager, get_dev_session

    mgr = get_dev_session_manager()
    mgr.start_session()                         # call once at startup

    intent = mgr.resolve_followup("continue")   # before each request
    goal   = mgr.build_followup_goal(intent)    # synthesise goal if follow-up

    mgr.add_prompt(user_text, ai_response)      # after each turn
    mgr.undo_last_task()                        # on "undo" command

    ctx = get_dev_session()                     # read current session state
"""
from nova.session.manager import DevelopmentSessionManager
from nova.session.models import (
    DevelopmentSession,
    FollowupIntent,
    TaskRecord,
    UndoEntry,
)
from nova.session.intent_resolver import resolve_intent, is_followup


def get_dev_session_manager() -> DevelopmentSessionManager:
    """Return the singleton DevelopmentSessionManager."""
    return DevelopmentSessionManager()


def get_dev_session() -> DevelopmentSession | None:
    """Return the active DevelopmentSession, or None if not started."""
    return DevelopmentSessionManager().get_session()


__all__ = [
    # Manager
    "DevelopmentSessionManager",
    "get_dev_session_manager",
    "get_dev_session",
    # Models
    "DevelopmentSession",
    "FollowupIntent",
    "TaskRecord",
    "UndoEntry",
    # Resolver helpers
    "resolve_intent",
    "is_followup",
]
