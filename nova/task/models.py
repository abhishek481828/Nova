"""
nova.task.models
~~~~~~~~~~~~~~~~
Data models for the Task Execution Engine.
Defines TaskStatus, TaskStep, Task, and TaskReport.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    RETRYING = "retrying"
    PAUSED = "paused"
    CANCELLED = "cancelled"


@dataclass
class TaskStep:
    """
    A single step inside an execution task.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    action_type: str = "generic"
    status: TaskStatus = TaskStatus.PENDING
    dependencies: List[str] = field(default_factory=list)  # IDs of steps this step depends on
    retry_count: int = 3
    timeout: float = 60.0
    expected_artifact: str = ""  # e.g., file path or validation check
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Results populated during execution
    files_created: List[str] = field(default_factory=list)
    files_modified: List[str] = field(default_factory=list)
    error_message: Optional[str] = None
    duration_s: float = 0.0


@dataclass
class Task:
    """
    Represent an end-to-end task executing a user goal.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal_description: str = ""
    status: TaskStatus = TaskStatus.PENDING
    steps: List[TaskStep] = field(default_factory=list)
    
    # Timing and progress tracking
    created_at: float = field(default_factory=time.time)
    finished_at: Optional[float] = None
    duration_s: float = 0.0
    
    # Auditing / Rollback
    rollbacks_executed: List[str] = field(default_factory=list)  # List of step descriptions rolled back
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class TaskReport:
    """
    Final output report compiled after task execution finishes.
    """
    task_id: str
    goal: str
    status: TaskStatus
    steps_executed: int
    steps_completed: int
    steps_failed: int
    files_created: List[str]
    files_modified: List[str]
    rollbacks: List[str]
    total_execution_time_s: float
    validation_status: bool
    validation_errors: List[str]
    metadata: Dict[str, Any]
