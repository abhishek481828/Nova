"""
nova.task
~~~~~~~~~
Task Execution Engine — Public API.
Allows Nova to plan, execute, verify, and rollback software development tasks.
"""
from nova.task.engine import TaskExecutionEngine
from nova.task.models import Task, TaskStep, TaskStatus, TaskReport

def get_task_execution_engine() -> TaskExecutionEngine:
    """
    Get the singleton TaskExecutionEngine service.
    """
    return TaskExecutionEngine()

__all__ = [
    "TaskExecutionEngine",
    "Task",
    "TaskStep",
    "TaskStatus",
    "TaskReport",
    "get_task_execution_engine",
]
