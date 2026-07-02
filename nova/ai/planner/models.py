import os
import time
import uuid
import json
import logging
import threading
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("nova.ai.planner")


from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict

@dataclass
class Goal:
    """
    Represents a high-level goal defined by the user or system.
    """
    description: str
    priority: str = "medium"  # low, medium, high
    target_skills: List[str] = field(default_factory=list)
    target_resources: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not self.description or not self.description.strip():
            raise ValueError("Goal description cannot be empty.")
        if self.priority not in ("low", "medium", "high"):
            raise ValueError("Goal priority must be 'low', 'medium', or 'high'.")

@dataclass
class RecoveryPolicy:
    """
    Specifies how the planner and execution manager recover from step failures.
    """
    strategy: str = "retry"  # retry, skip, alternative_step, fallback_skill, rollback, partial_completion
    max_retries: int = 3
    fallback_skills: List[str] = field(default_factory=list)
    allow_partial: bool = False
    alternative_step_desc: Optional[str] = None
    alternative_step_action: Optional[str] = None
    rollback_step_descs: List[str] = field(default_factory=list)

@dataclass
class PlanStep:
    """
    A single task or step inside an execution plan. Can be a leaf or a parent.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    action_type: str = "generic"
    required_skill: str = "generic"
    dependencies: List[str] = field(default_factory=list)  # List of PlanStep IDs this step depends on
    expected_output: str = ""
    status: str = "pending"  # pending, executing, completed, failed, cancelled, skipped
    retry_count: int = 3
    timeout: float = 30.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_id: Optional[str] = None  # Parent step ID in hierarchy
    child_ids: List[str] = field(default_factory=list)  # List of child step IDs
    required_resources: List[str] = field(default_factory=list)  # Step level resource requirements
    required_skills: List[str] = field(default_factory=list)  # List of required skills automatically selected
    recovery_policy: Optional[RecoveryPolicy] = None
    expected_artifact: str = ""  # The artifact produced by this step (e.g. file, directory, or status check)
    required_artifacts: List[str] = field(default_factory=list)  # Artifacts this step requires before execution

@dataclass
class Plan:
    """
    An ordered/dependency-mapped set of steps designed to fulfill a user goal.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal: Goal = field(default_factory=lambda: Goal(""))
    goal_description: str = ""
    priority: str = "medium"
    status: str = "pending"  # pending, validated, executed, failed, cancelled, executing, paused
    estimated_complexity: str = "low"  # low, medium, high
    estimated_duration: float = 0.0  # seconds
    creation_timestamp: float = field(default_factory=time.time)
    created_at: float = field(default_factory=time.time)  # backward compatibility
    dependencies: List[str] = field(default_factory=list)
    steps: List[PlanStep] = field(default_factory=list)
    required_skills: List[str] = field(default_factory=list)
    required_resources: List[str] = field(default_factory=list)
    validation_status: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    required_artifacts: List[str] = field(default_factory=list)  # Inferred required deliverables/artifacts
    required_dependencies: List[str] = field(default_factory=list)  # Inferred package/tool dependencies
    risk_analysis: Dict[str, Any] = field(default_factory=dict)  # Planning risk metrics and mitigations
    expected_outputs: List[str] = field(default_factory=list)  # Final files or conditions to be produced

    def __post_init__(self) -> None:
        if not self.goal_description and self.goal:
            self.goal_description = self.goal.description
        if self.created_at and not self.creation_timestamp:
            self.creation_timestamp = self.created_at
        elif self.creation_timestamp and not self.created_at:
            self.created_at = self.creation_timestamp

@dataclass
class PlanningContext:
    """
    Context parameters containing read-only Working Memory and Long-Term Memory snapshots.
    """
    working_memory: Optional[Any] = None
    long_term_memory: Optional[Any] = None
    additional_metadata: Dict[str, Any] = field(default_factory=dict)

class ValidationReport:
    """
    Detailed report containing validation results, errors, warnings, and metrics.
    Acts as a tuple (valid: bool, errors: List[str]) for backward compatibility.
    """
    def __init__(
        self,
        valid: bool,
        errors: List[str],
        warnings: List[str] = None,
        metrics: Dict[str, Any] = None
    ) -> None:
        self.valid = valid
        self.errors = errors
        self.warnings = warnings or []
        self.metrics = metrics or {}

    def __iter__(self):
        return iter((self.valid, self.errors))

    def __getitem__(self, index):
        return (self.valid, self.errors)[index]

    def __repr__(self) -> str:
        return f"ValidationReport(valid={self.valid}, errors={self.errors}, warnings={self.warnings}, metrics={self.metrics})"

@dataclass
class PlanningResult:
    """
    Output model returned by the planner containing generated plans or validation errors.
    """
    success: bool
    plan: Optional[Plan] = None
    errors: List[str] = field(default_factory=list)
    latency: float = 0.0

@dataclass
class PlanProgress:
    """
    Status metrics and progress report for plan execution.
    """
    completed_steps: List[str] = field(default_factory=list)
    failed_steps: List[str] = field(default_factory=list)
    running_steps: List[str] = field(default_factory=list)
    waiting_steps: List[str] = field(default_factory=list)
    skipped_steps: List[str] = field(default_factory=list)
    completion_percentage: float = 0.0
    estimated_remaining_time: float = 0.0
    execution_timeline: List[Dict[str, Any]] = field(default_factory=list)


