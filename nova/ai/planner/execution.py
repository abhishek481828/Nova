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
from nova.ai.planner.models import (
    Goal,
    RecoveryPolicy,
    PlanStep,
    Plan,
    PlanningContext,
    ValidationReport,
    PlanningResult,
    PlanProgress,
)
from nova.ai.planner.rules import determine_required_skills

class PlanExecutionInterface(ABC):
    """
    Abstract execution interface for submitting and tracking plans.
    """
    @abstractmethod
    def start_plan(self, plan: Plan) -> None:
        pass

    @abstractmethod
    def pause_plan(self, plan_id: str) -> None:
        pass

    @abstractmethod
    def resume_plan(self, plan_id: str) -> None:
        pass

    @abstractmethod
    def cancel_plan(self, plan_id: str) -> None:
        pass

    @abstractmethod
    def get_status(self, plan_id: str) -> str:
        pass

class PlanExecutionManager(PlanExecutionInterface):
    """
    Concrete manager implementing state transitions and progress tracking for plans,
    integrating with Working Memory without executing actual browser or shell actions.
    Uses reentrant locking to guarantee thread safety.
    """
    def __init__(self, working_memory: Optional[Any] = None) -> None:
        self.active_plans: Dict[str, Plan] = {}
        self.working_memory = working_memory
        self._lock = threading.RLock()

    def _record_timeline(self, plan: Plan, step_id: str, step_desc: str, status: str) -> None:
        with self._lock:
            timeline = plan.metadata.setdefault("execution_timeline", [])
            timeline.append({
                "step_id": step_id,
                "description": step_desc,
                "status": status,
                "timestamp": time.time()
            })

    def _publish_progress_to_wm(self, plan: Plan) -> None:
        if self.working_memory and hasattr(self.working_memory, "set"):
            try:
                progress = self.get_progress(plan.id)
                self.working_memory.set("active_plan_progress", asdict(progress))
            except Exception as e:
                logger.error(f"Failed to publish progress to working memory: {e}")

    def start_plan(self, plan: Plan) -> None:
        logger.info(f"Execution Manager: Starting plan {plan.id}")
        with self._lock:
            plan.status = "executing"
            self.active_plans[plan.id] = plan
            
            # Reset timeline in metadata
            plan.metadata["execution_timeline"] = []
            self._record_timeline(plan, "plan_root", plan.goal_description, "executing")

            # Initial level step statuses set to executing
            for step in plan.steps:
                if not step.dependencies:
                    step.status = "executing"
                    self._record_timeline(plan, step.id, step.description, "executing")
                    
            self._publish_progress_to_wm(plan)

    def pause_plan(self, plan_id: str) -> None:
        logger.info(f"Execution Manager: Pausing plan {plan_id}")
        with self._lock:
            plan = self.active_plans.get(plan_id)
            if not plan:
                raise KeyError(f"Plan with ID '{plan_id}' is not currently managed.")
            
            plan.status = "paused"
            self._record_timeline(plan, "plan_root", plan.goal_description, "paused")
            for step in plan.steps:
                if step.status == "executing":
                    step.status = "paused"
                    self._record_timeline(plan, step.id, step.description, "paused")
                    
            self._publish_progress_to_wm(plan)

    def resume_plan(self, plan_id: str) -> None:
        logger.info(f"Execution Manager: Resuming plan {plan_id}")
        with self._lock:
            plan = self.active_plans.get(plan_id)
            if not plan:
                raise KeyError(f"Plan with ID '{plan_id}' is not currently managed.")
            
            plan.status = "executing"
            self._record_timeline(plan, "plan_root", plan.goal_description, "executing")
            for step in plan.steps:
                if step.status == "paused":
                    step.status = "executing"
                    self._record_timeline(plan, step.id, step.description, "executing")
                    
            self._publish_progress_to_wm(plan)

    def cancel_plan(self, plan_id: str) -> None:
        logger.info(f"Execution Manager: Cancelling plan {plan_id}")
        with self._lock:
            plan = self.active_plans.get(plan_id)
            if not plan:
                raise KeyError(f"Plan with ID '{plan_id}' is not currently managed.")
            
            plan.status = "cancelled"
            self._record_timeline(plan, "plan_root", plan.goal_description, "cancelled")
            for step in plan.steps:
                if step.status in ("pending", "executing", "paused"):
                    step.status = "cancelled"
                    self._record_timeline(plan, step.id, step.description, "cancelled")
                    
            self._publish_progress_to_wm(plan)

    def update_step_status(self, plan_id: str, step_id: str, new_status: str) -> None:
        logger.info(f"Execution Manager: Updating step {step_id} to status {new_status}")
        with self._lock:
            plan = self.active_plans.get(plan_id)
            if not plan:
                raise KeyError(f"Plan with ID '{plan_id}' is not currently managed.")
                
            step = next((s for s in plan.steps if s.id == step_id), None)
            if not step:
                raise KeyError(f"Step with ID '{step_id}' does not exist in plan '{plan_id}'.")
                
            step.status = new_status
            self._record_timeline(plan, step_id, step.description, new_status)
            
            self._publish_progress_to_wm(plan)

    def prepare_recovery_plan(self, plan_id: str, failed_step_id: str) -> Plan:
        logger.info(f"Execution Manager: Preparing recovery plan for plan {plan_id}, failed step {failed_step_id}")
        with self._lock:
            plan = self.active_plans.get(plan_id)
            if not plan:
                raise KeyError(f"Plan with ID '{plan_id}' is not currently managed.")
                
            step = next((s for s in plan.steps if s.id == failed_step_id), None)
            if not step:
                raise KeyError(f"Step with ID '{failed_step_id}' does not exist in plan '{plan_id}'.")
                
            if step.status != "failed":
                step.status = "failed"
                self._record_timeline(plan, failed_step_id, step.description, "failed")
                
            policy = step.recovery_policy
            if not policy:
                logger.info(f"No recovery policy found on step {failed_step_id}. Defaulting to fail plan.")
                plan.status = "failed"
                self._publish_progress_to_wm(plan)
                return plan

            strategy = policy.strategy
            logger.info(f"Executing recovery strategy '{strategy}' for step '{step.description}'")

            if strategy == "retry":
                if step.retry_count > 0:
                    step.retry_count -= 1
                    step.status = "pending"
                    self._record_timeline(plan, failed_step_id, step.description, "retry_triggered")
                    logger.info(f"Retry triggered for step {failed_step_id}. Attempts remaining: {step.retry_count}")
                else:
                    logger.warning(f"Retry budget exhausted for step {failed_step_id}. Failing plan.")
                    plan.status = "failed"
                    self._record_timeline(plan, failed_step_id, step.description, "retry_exhausted")
                    
            elif strategy == "skip":
                step.status = "skipped"
                self._record_timeline(plan, failed_step_id, step.description, "skipped")
                logger.info(f"Skip triggered for step {failed_step_id}.")
                
            elif strategy == "alternative_step":
                if policy.alternative_step_desc:
                    # 1. Create alternative step
                    alt_step_id = str(uuid.uuid4())
                    alt_step = PlanStep(
                        id=alt_step_id,
                        description=policy.alternative_step_desc,
                        action_type=policy.alternative_step_action or "generic",
                        required_skill="generic",
                        dependencies=list(step.dependencies),  # inherits dependencies of the failed step
                        status="pending",
                        parent_id=step.parent_id
                    )
                    
                    # 2. Automatically determine skills for alternative step
                    alt_skills = determine_required_skills(alt_step.description, alt_step.action_type)
                    alt_step.required_skills = alt_skills
                    alt_step.required_skill = alt_skills[0] if alt_skills else "generic"
                    
                    # 3. Insert into plan
                    plan.steps.append(alt_step)
                    
                    # 4. Redirect parent child links and downstream dependency links
                    if step.parent_id:
                        parent_step = next((s for s in plan.steps if s.id == step.parent_id), None)
                        if parent_step:
                            parent_step.child_ids.append(alt_step_id)
                            
                    for s in plan.steps:
                        if step.id in s.dependencies:
                            s.dependencies = [alt_step_id if d == step.id else d for d in s.dependencies]
                            
                    # Mark original failed step as skipped (completed execution replacement)
                    step.status = "skipped"
                    
                    self._record_timeline(plan, failed_step_id, step.description, "alternative_injected")
                    logger.info(f"Injected alternative step {alt_step_id} for failed step {failed_step_id}")
                else:
                    plan.status = "failed"
                    
            elif strategy == "fallback_skill":
                if policy.fallback_skills:
                    step.required_skills = list(policy.fallback_skills)
                    step.required_skill = policy.fallback_skills[0]
                    step.status = "pending"
                    self._record_timeline(plan, failed_step_id, step.description, "fallback_skill_applied")
                    logger.info(f"Applied fallback skills {policy.fallback_skills} to step {failed_step_id}")
                else:
                    plan.status = "failed"
                    
            elif strategy == "rollback":
                # Append rollback steps and set plan status to failed/rollback
                plan.status = "failed"
                self._record_timeline(plan, failed_step_id, step.description, "rollback_triggered")
                
                rollback_ids = []
                for desc in policy.rollback_step_descs:
                    rb_id = str(uuid.uuid4())
                    rb_step = PlanStep(
                        id=rb_id,
                        description=desc,
                        action_type="command_execution",
                        required_skill="system",
                        required_skills=["system"],
                        status="pending"
                    )
                    plan.steps.append(rb_step)
                    rollback_ids.append(rb_id)
                    self._record_timeline(plan, rb_id, desc, "rollback_step_queued")
                    
                logger.info(f"Queued rollback steps: {policy.rollback_step_descs}")
                
            elif strategy == "partial_completion":
                if policy.allow_partial:
                    step.status = "skipped"
                    self._record_timeline(plan, failed_step_id, step.description, "partial_completion_allowed")
                    logger.info(f"Partial completion allowed for step {failed_step_id}. Skipping and continuing plan.")
                else:
                    plan.status = "failed"
                    
            self._publish_progress_to_wm(plan)
            return plan

    def get_status(self, plan_id: str) -> str:
        with self._lock:
            plan = self.active_plans.get(plan_id)
            if not plan:
                raise KeyError(f"Plan with ID '{plan_id}' is not currently managed.")
            return plan.status

    def get_progress(self, plan_id: str) -> PlanProgress:
        with self._lock:
            plan = self.active_plans.get(plan_id)
            if not plan:
                raise KeyError(f"Plan with ID '{plan_id}' is not currently managed.")
                
            completed = []
            failed = []
            running = []
            waiting = []
            skipped = []
            
            # Compile lists by status
            for s in plan.steps:
                if s.status == "completed":
                    completed.append(s.id)
                elif s.status == "failed":
                    failed.append(s.id)
                elif s.status == "executing":
                    running.append(s.id)
                elif s.status == "paused" or s.status == "pending":
                    waiting.append(s.id)
                elif s.status == "skipped":
                    skipped.append(s.id)
                elif s.status == "cancelled":
                    skipped.append(s.id)
                    
            # Completion percentage is calculated based on leaf steps
            leaves = [s for s in plan.steps if not s.child_ids]
            completed_leaves = [s for s in leaves if s.status == "completed"]
            skipped_leaves = [s for s in leaves if s.status == "skipped"]
            
            total_leaves = len(leaves)
            finished_leaves = len(completed_leaves) + len(skipped_leaves)
            
            completion_pct = (finished_leaves / total_leaves) * 100.0 if total_leaves > 0 else 0.0
            
            # Remaining time is estimated by summing timeouts of active/pending leaf steps
            remaining_time = sum(s.timeout for s in leaves if s.status in ("pending", "executing", "paused"))
            
            timeline = plan.metadata.get("execution_timeline", [])
            
            return PlanProgress(
                completed_steps=completed,
                failed_steps=failed,
                running_steps=running,
                waiting_steps=waiting,
                skipped_steps=skipped,
                completion_percentage=completion_pct,
                estimated_remaining_time=remaining_time,
                execution_timeline=list(timeline)
            )


