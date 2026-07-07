"""
nova.edit
~~~~~~~~~
Code Editing Engine — public API.

Quick-start::
    from nova.edit import get_code_editor
    
    editor = get_code_editor()
    result = editor.rename_symbol("nova/core/memory.py", "WorkingMemory", "WorkingMemoryV2")
    if result.success:
        print(result.diff)
"""
from nova.edit.editor import CodeEditor
from nova.edit.operations import EditResult, EditOperation, EditKind

def get_code_editor() -> "CodeEditor":
    """
    Get the singleton CodeEditor service.
    """
    return CodeEditor()

__all__ = [
    "CodeEditor",
    "EditResult",
    "EditOperation",
    "EditKind",
    "get_code_editor",
]
