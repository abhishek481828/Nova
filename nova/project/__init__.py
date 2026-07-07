"""
nova.project
~~~~~~~~~~~~
Project Awareness Engine — public API.

Quick-start::

    from nova.project import get_project_context, ProjectAwarenessEngine

    ctx = get_project_context()      # returns cached context or None
    # or trigger a scan:
    engine = ProjectAwarenessEngine()
    ctx = engine.scan(Path.cwd())
    print(ctx.summary)
"""

from nova.project.context import FileNode, LanguageInfo, ProjectContext
from nova.project.engine import ProjectAwarenessEngine

# Module-level convenience accessor
def get_project_context():
    """
    Return the current ProjectContext from the singleton engine, or None.
    This is the primary entry point for all Nova components that need
    project awareness without managing the engine lifecycle themselves.
    """
    return ProjectAwarenessEngine().get_context()


__all__ = [
    "ProjectAwarenessEngine",
    "ProjectContext",
    "LanguageInfo",
    "FileNode",
    "get_project_context",
]
