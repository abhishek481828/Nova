import time
import uuid
import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger("nova.planner")

@dataclass
class Goal:
    """
    Represents a high-level goal defined by the user or system.
    """
    description: str
    priority: str = "medium"  # low, medium, high
    target_skills: List[str] = field(default_factory=list)
    target_resources: List[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.description or not self.description.strip():
            raise ValueError("Goal description cannot be empty.")
        if self.priority not in ("low", "medium", "high"):
            raise ValueError("Goal priority must be 'low', 'medium', or 'high'.")

@dataclass
class PlanStep:
    """
    A single, granular task or step inside a larger execution plan.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: str = ""
    action_type: str = "generic"
    required_skill: str = "generic"
    dependencies: List[str] = field(default_factory=list)  # List of PlanStep IDs this step depends on
    expected_output: str = ""
    status: str = "pending"  # pending, executing, completed, failed, cancelled
    retry_count: int = 3
    timeout: float = 30.0
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class Plan:
    """
    An ordered/dependency-mapped set of steps designed to fulfill a user goal.
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    goal: Goal = field(default_factory=lambda: Goal(""))
    priority: str = "medium"
    status: str = "pending"  # pending, validated, executed, failed, cancelled
    estimated_complexity: str = "low"  # low, medium, high
    estimated_duration: float = 0.0  # seconds
    created_at: float = field(default_factory=time.time)
    dependencies: List[str] = field(default_factory=list)
    steps: List[PlanStep] = field(default_factory=list)
    required_skills: List[str] = field(default_factory=list)
    required_resources: List[str] = field(default_factory=list)
    validation_status: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PlanningContext:
    """
    Context parameters containing read-only Working Memory and Long-Term Memory snapshots.
    """
    working_memory: Optional[Any] = None
    long_term_memory: Optional[Any] = None
    additional_metadata: Dict[str, Any] = field(default_factory=dict)

@dataclass
class PlanningResult:
    """
    Output model returned by the planner containing generated plans or validation errors.
    """
    success: bool
    plan: Optional[Plan] = None
    errors: List[str] = field(default_factory=list)
    latency: float = 0.0

class Planner:
    """
    Executive function for Nova. Translates user goals into structured plans
    without executing any action steps directly.
    """
    def __init__(
        self,
        working_memory: Optional[Any] = None,
        ltm_manager: Optional[Any] = None
    ) -> None:
        self.working_memory = working_memory
        self.ltm_manager = ltm_manager

    def create_plan(self, goal: Goal, context: Optional[PlanningContext] = None) -> PlanningResult:
        """
        Generates a Plan step-by-step from user goals based on keyword mappings.
        Does NOT execute plans or modify memory.
        """
        start_time = time.time()
        logger.info(f"Generating execution plan for goal: '{goal.description}'")

        try:
            goal.validate()
        except ValueError as e:
            logger.error(f"Goal validation failed: {e}")
            return PlanningResult(
                success=False,
                errors=[str(e)],
                latency=time.time() - start_time
            )

        steps: List[PlanStep] = []
        desc_lower = goal.description.lower()

        # Simple heuristic plan generation (without deep reasoning execution)
        if "open chrome" in desc_lower and "youtube" in desc_lower:
            step1 = PlanStep(
                description="Open Chromium Browser",
                action_type="chromium_action",
                required_skill="browser",
                expected_output="Chromium browser active"
            )
            step2 = PlanStep(
                description="Navigate to YouTube and search",
                action_type="chromium_action",
                required_skill="browser",
                dependencies=[step1.id],
                expected_output="YouTube video results displayed"
            )
            steps.extend([step1, step2])

        elif "git pull" in desc_lower and "test" in desc_lower:
            step1 = PlanStep(
                description="Execute git pull in project",
                action_type="git_action",
                required_skill="git",
                expected_output="Repository updated to origin main"
            )
            step2 = PlanStep(
                description="Run automated test suite",
                action_type="command_execution",
                required_skill="shell",
                dependencies=[step1.id],
                expected_output="Test execution completed",
                timeout=60.0
            )
            steps.extend([step1, step2])

        else:
            # Fallback to generic single step
            steps.append(
                PlanStep(
                    description=f"Fulfill request: {goal.description}",
                    action_type="generic_action",
                    required_skill="generic",
                    expected_output="Request completed successfully"
                )
            )

        # Build plan object
        plan = Plan(
            goal=goal,
            priority=goal.priority,
            steps=steps,
            required_skills=list({s.required_skill for s in steps}),
            estimated_complexity=self.estimate_complexity(steps),
            estimated_duration=self.estimate_duration(steps)
        )

        # Validate the generated plan graph
        valid, errors = self.validate_plan(plan)
        plan.validation_status = valid
        if valid:
            plan.status = "validated"
            logger.info("Execution plan validated successfully.")
            return PlanningResult(
                success=True,
                plan=plan,
                latency=time.time() - start_time
            )
        else:
            plan.status = "failed"
            logger.error(f"Execution plan graph validation failed: {errors}")
            return PlanningResult(
                success=False,
                plan=plan,
                errors=errors,
                latency=time.time() - start_time
            )

    def validate_plan(self, plan: Plan) -> Tuple[bool, List[str]]:
        """
        Validates plan structural parameters and detects cyclic step dependencies.
        Uses topological sorting / DFS recursion stack track checks.
        """
        errors: List[str] = []
        step_ids = {step.id for step in plan.steps}

        # 1. Validate dependency existence
        for step in plan.steps:
            for dep in step.dependencies:
                if dep not in step_ids:
                    errors.append(f"Step '{step.description}' has unresolved dependency: '{dep}'")

        if errors:
            return False, errors

        # 2. Cycle detection (DFS path tracing)
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def has_cycle(step_id: str) -> bool:
            visited.add(step_id)
            rec_stack.add(step_id)

            # Find matching step
            step = next((s for s in plan.steps if s.id == step_id), None)
            if step:
                for dep in step.dependencies:
                    if dep not in visited:
                        if has_cycle(dep):
                            return True
                    elif dep in rec_stack:
                        return True

            rec_stack.remove(step_id)
            return False

        for step in plan.steps:
            if step.id not in visited:
                if has_cycle(step.id):
                    errors.append("Dependency cycle detected in plan steps.")
                    return False, errors

        return True, []

    def estimate_complexity(self, steps: List[PlanStep]) -> str:
        """Heuristic complexity mapping based on step count and dependency counts."""
        if not steps:
            return "low"
        
        dep_count = sum(len(step.dependencies) for step in steps)
        if len(steps) <= 1 and dep_count == 0:
            return "low"
        elif len(steps) <= 3 and dep_count <= 2:
            return "medium"
        return "high"

    def estimate_duration(self, steps: List[PlanStep]) -> float:
        """Estimates duration by summing steps timeouts."""
        return sum(step.timeout for step in steps)

    def export_plan(self, plan: Plan) -> str:
        """Serializes Plan and subdataclasses to a JSON string representation."""
        logger.info(f"Exporting plan: '{plan.id}'")
        return json.dumps(asdict(plan), indent=2)

    def import_plan(self, plan_json: str) -> Plan:
        """Deserializes a JSON string into a structured Plan object."""
        logger.info("Importing plan from JSON string.")
        data = json.loads(plan_json)
        
        goal_data = data.get("goal", {})
        goal = Goal(
            description=goal_data.get("description", ""),
            priority=goal_data.get("priority", "medium"),
            target_skills=goal_data.get("target_skills", []),
            target_resources=goal_data.get("target_resources", [])
        )

        steps_data = data.get("steps", [])
        steps = []
        for s in steps_data:
            steps.append(
                PlanStep(
                    id=s.get("id"),
                    description=s.get("description", ""),
                    action_type=s.get("action_type", "generic"),
                    required_skill=s.get("required_skill", "generic"),
                    dependencies=s.get("dependencies", []),
                    expected_output=s.get("expected_output", ""),
                    status=s.get("status", "pending"),
                    retry_count=s.get("retry_count", 3),
                    timeout=s.get("timeout", 30.0),
                    metadata=s.get("metadata", {})
                )
            )

        return Plan(
            id=data.get("id", str(uuid.uuid4())),
            goal=goal,
            priority=data.get("priority", "medium"),
            status=data.get("status", "pending"),
            estimated_complexity=data.get("estimated_complexity", "low"),
            estimated_duration=data.get("estimated_duration", 0.0),
            created_at=data.get("created_at", time.time()),
            dependencies=data.get("dependencies", []),
            steps=steps,
            required_skills=data.get("required_skills", []),
            required_resources=data.get("required_resources", []),
            validation_status=data.get("validation_status", False),
            metadata=data.get("metadata", {})
        )

    def cancel_plan(self, plan: Plan) -> Plan:
        """Sets plan status to cancelled."""
        logger.info(f"Cancelling plan: '{plan.id}'")
        plan.status = "cancelled"
        for step in plan.steps:
            step.status = "cancelled"
        return plan
