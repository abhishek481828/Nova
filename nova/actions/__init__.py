import importlib
import os
import pkgutil
from typing import Dict
from nova.actions.base import BaseAction
from nova.logger import log_error

def get_action_dispatcher() -> Dict[str, BaseAction]:
    """
    Dynamically discovers and loads all action modules in this folder.
    Returns a dict mapping action_name -> BaseAction instance.
    """
    dispatcher: Dict[str, BaseAction] = {}
    package_dir = os.path.dirname(__file__)
    
    for _, module_name, is_pkg in pkgutil.iter_modules([package_dir]):
        if is_pkg or module_name == "base":
            continue
            
        full_module_name = f"nova.actions.{module_name}"
        try:
            module = importlib.import_module(full_module_name)
            
            # Inspect classes in the module
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, BaseAction)
                    and attr is not BaseAction
                ):
                    action_instance = attr()
                    dispatcher[action_instance.action_name] = action_instance
        except Exception as e:
            log_error(f"Failed to dynamically import module {full_module_name}", e)
            
    return dispatcher
