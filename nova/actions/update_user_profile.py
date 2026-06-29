from typing import Any, Dict
from nova.actions.base import BaseAction
from nova.state import StateManager

class UpdateUserProfileAction(BaseAction):
    @property
    def action_name(self) -> str:
        return "update_user_profile"

    def execute(self, params: Dict[str, Any]) -> str:
        details = params.get("details", {})
        if not isinstance(details, dict) or not details:
            return "Error: No profile details provided to update."
            
        StateManager.update_user_profile(details)
        
        # Build a nice response message to the user acknowledging the saved details
        details_list = [f"{k}: {v}" for k, v in details.items()]
        return f"Got it! I have saved your details: {', '.join(details_list)}."
