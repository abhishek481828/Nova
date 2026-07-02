import time
from typing import Optional
from nova.logger import logger

def infer_topic(intent: Optional[str], query: str, actions: list) -> Optional[str]:
    if not intent:
        return "general"
    if actions and isinstance(actions, list):
        action = actions[0]
        for param in ["query", "url", "app", "package", "text"]:
            if action.get(param):
                return f"{intent}: {action.get(param)}"
    return intent

def update_working_memory_after_turn(
    working_memory,
    user_message: str,
    assistant_reply: str,
    intent: Optional[str],
    topic: Optional[str]
) -> None:
    from nova.core.memory import Interaction
    prev_topic = working_memory.get("current_topic")
    prev_intent = working_memory.get("current_intent")

    working_memory.set("previous_topic", prev_topic)
    working_memory.set("previous_intent", prev_intent)
    working_memory.set("current_topic", topic)
    working_memory.set("current_intent", intent)
    working_memory.set("previous_command", user_message)
    working_memory.set("previous_assistant_reply", assistant_reply)

    interaction = Interaction(
        user_prompt=user_message,
        assistant_response=assistant_reply,
        intent=intent,
        timestamp=time.time()
    )
    working_memory.append_history(interaction)
    session_conv = list(working_memory.get("current_conversation") or [])
    session_conv.append(interaction)
    working_memory.set("current_conversation", session_conv)
    logger.info("Automatically updated working memory with user interaction details.")
