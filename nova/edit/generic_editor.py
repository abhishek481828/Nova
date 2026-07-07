"""
nova.edit.generic_editor
~~~~~~~~~~~~~~~~~~~~~~~~
Generic fallback editor for files that are not Python or JavaScript/TypeScript.
Performs safe block replacements with verification of uniqueness.
"""
from __future__ import annotations

import logging

logger = logging.getLogger("nova.edit.generic_editor")

def replace_block(content: str, old_block: str, new_block: str) -> str:
    """
    Replace *old_block* with *new_block* in the file content.
    Validates that *old_block* occurs EXACTLY once in the content before modifying.
    
    Raises ValueError if block is not found or is ambiguous.
    """
    count = content.count(old_block)
    if count == 0:
        raise ValueError("The target block to replace was not found in the file content.")
    if count > 1:
        raise ValueError("The target block is ambiguous and was found multiple times in the file.")
        
    return content.replace(old_block, new_block, 1)
