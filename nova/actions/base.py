import time
from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseAction(ABC):
    """
    Abstract Base Class for all Nova actions.
    Every subclass inside nova/actions/ must implement this.
    """
    
    _shared_working_memory = None

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        
        # Check if execute exists and is not an abstract placeholder
        execute_fn = getattr(cls, "execute", None)
        if execute_fn is not None and not getattr(execute_fn, "__is_abstractmethod__", False):
            # Avoid double-wrapping
            if not getattr(execute_fn, "_is_wrapped", False):
                orig_execute = execute_fn
                
                def wrapped_execute(self, params: Dict[str, Any]) -> str:
                    # Find working memory context
                    wm = getattr(self, "working_memory", None) or BaseAction._shared_working_memory
                    
                    action_name = self.action_name
                    module_name = self.__class__.__module__
                    category = module_name.split(".")[-1] if "." in module_name else "general"
                    
                    start_time = time.time()
                    success = False
                    result = None
                    error_message = None
                    
                    try:
                        result = orig_execute(self, params)
                        success = True
                        return result
                    except Exception as e:
                        error_message = str(e)
                        raise e
                    finally:
                        elapsed = time.time() - start_time
                        if wm is not None:
                            try:
                                action_record = {
                                    "action_name": action_name,
                                    "category": category,
                                    "parameters": params,
                                    "result": result if success else None,
                                    "success": success,
                                    "execution_time": elapsed,
                                    "returned_data": result if success else None,
                                    "error_message": error_message,
                                    "timestamp": start_time
                                }
                                recent = list(wm.get("recent_actions") or [])
                                recent.append(action_record)
                                if len(recent) > 100:
                                    recent.pop(0)
                                wm.set("recent_actions", recent)
                            except Exception as sync_err:
                                import logging
                                logging.getLogger("nova").debug(f"Failed to record action execution trace: {sync_err}")
                
                wrapped_execute._is_wrapped = True
                cls.execute = wrapped_execute
    
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
