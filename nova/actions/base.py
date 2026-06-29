from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseAction(ABC):
    """
    Abstract Base Class for all Nova actions.
    Every subclass inside nova/actions/ must implement this.
    """
    
    @property
    @abstractmethod
    def action_name(self) -> str:
        """
        The key identifier of the action corresponding to the 
        JSON 'action' field from the AI parsing response.
        """
        pass
        
    @abstractmethod
    def execute(self, params: Dict[str, Any]) -> str:
        """
        Execute the action logic using the provided parameters.
        Returns a string summarizing the result of the action.
        """
        pass

    @property
    def is_long_running(self) -> bool:
        """
        Returns whether this action is expected to take noticeable time (> 1 second).
        Subclasses can override this. Defaults to False.
        """
        return False
