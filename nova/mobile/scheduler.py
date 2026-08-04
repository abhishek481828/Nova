"""Nova v3.0 — Task Scheduler Python Bindings."""

import uuid
from typing import Callable, Dict, Any


class MobileTask:
    def __init__(self, task_id: str, name: str, priority: str = "MEDIUM", action: Callable[[], bool] = None):
        self.id = task_id or str(uuid.uuid4())
        self.name = name
        self.priority = priority
        self.action = action or (lambda: True)


class TaskScheduler:
    def __init__(self):
        self.is_running = False
        self.tasks: Dict[str, MobileTask] = {}

    def initialize(self):
        self.is_running = True

    def schedule_immediate(self, task: MobileTask) -> str:
        self.tasks[task.id] = task
        if task.action:
            task.action()
        return task.id

    def cancel_all(self):
        self.tasks.clear()
        self.is_running = False
