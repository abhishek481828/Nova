import time
import uuid
import logging
import threading
from typing import Any, Dict, List, Optional
from nova.ai.planner import Plan, PlanStep, RecoveryPolicy, determine_required_skills
from nova.core.executor import CommandExecutor

logger = logging.getLogger("nova.ai.reasoning")

class ExecutionState:
    READY = "READY"
    VALIDATED = "VALIDATED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"

class PlanQueue:
    """
    Thread-safe queue for managing generated Plans and their execution states.
    """
    def __init__(self) -> None:
        self._plans: Dict[str, Plan] = {}
        self._lock = threading.RLock()

    def add_plan(self, plan: Plan) -> None:
        with self._lock:
            self._plans[plan.id] = plan

    def get_plan(self, plan_id: str) -> Optional[Plan]:
        with self._lock:
            return self._plans.get(plan_id)

    def remove_plan(self, plan_id: str) -> None:
        with self._lock:
            self._plans.pop(plan_id, None)

    def list_plans(self) -> List[Plan]:
        with self._lock:
            return list(self._plans.values())

class ExecutionEngine:
    """
    Executes validated plans step-by-step, tracks real-time progress, validates browser state,
    applies step-level recovery strategies, and updates Working Memory.
    """
    def __init__(
        self,
        working_memory: Optional[Any] = None,
        action_dispatcher: Optional[Dict[str, Any]] = None,
        approval_required: bool = True
    ) -> None:
        self.working_memory = working_memory
        self.action_dispatcher = action_dispatcher
        self.approval_required = approval_required
        self.queue = PlanQueue()
        self._lock = threading.RLock()
        self._threads: Dict[str, threading.Thread] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self.telemetry: Dict[str, Dict[str, Any]] = {}

    def submit_plan(self, plan: Plan) -> None:
        logger.info(f"ExecutionEngine: Submitting plan {plan.id} for goal: '{plan.goal_description}'")
        with self._lock:
            plan.status = ExecutionState.VALIDATED
            self.queue.add_plan(plan)
            
            # Reset step statuses to pending
            for step in plan.steps:
                step.status = "pending"
                
            if self.approval_required:
                plan.status = ExecutionState.WAITING_APPROVAL
                logger.info(f"Plan {plan.id} is waiting for user approval.")
            else:
                plan.status = ExecutionState.READY
                logger.info(f"Plan {plan.id} is ready for execution.")
                
            self._update_working_memory(plan)

    def approve_plan(self, plan_id: str) -> None:
        logger.info(f"ExecutionEngine: Plan {plan_id} approved for execution.")
        with self._lock:
            plan = self.queue.get_plan(plan_id)
            if not plan:
                raise KeyError(f"Plan '{plan_id}' not found in queue.")
            
            plan.status = ExecutionState.RUNNING
            self._cancel_events[plan_id] = threading.Event()
            
            t = threading.Thread(target=self._execute_plan_thread, args=(plan_id,), daemon=True)
            self._threads[plan_id] = t
            t.start()
            
            self._update_working_memory(plan)

    def reject_plan(self, plan_id: str) -> None:
        logger.info(f"ExecutionEngine: Plan {plan_id} rejected by user.")
        with self._lock:
            plan = self.queue.get_plan(plan_id)
            if not plan:
                raise KeyError(f"Plan '{plan_id}' not found in queue.")
            plan.status = ExecutionState.CANCELLED
            for step in plan.steps:
                if step.status == "pending":
                    step.status = "cancelled"
            self._update_working_memory(plan)

    def pause_plan(self, plan_id: str) -> None:
        logger.info(f"ExecutionEngine: Pausing plan {plan_id}")
        with self._lock:
            plan = self.queue.get_plan(plan_id)
            if not plan:
                raise KeyError(f"Plan '{plan_id}' not found.")
            if plan.status == ExecutionState.RUNNING:
                plan.status = ExecutionState.PAUSED
                for s in plan.steps:
                    if s.status == "executing":
                        s.status = "paused"
                self._update_working_memory(plan)

    def resume_plan(self, plan_id: str) -> None:
        logger.info(f"ExecutionEngine: Resuming plan {plan_id}")
        with self._lock:
            plan = self.queue.get_plan(plan_id)
            if not plan:
                raise KeyError(f"Plan '{plan_id}' not found.")
            if plan.status == ExecutionState.PAUSED:
                plan.status = ExecutionState.RUNNING
                for s in plan.steps:
                    if s.status == "paused":
                        s.status = "executing"
                self._update_working_memory(plan)

    def cancel_plan(self, plan_id: str) -> None:
        logger.info(f"ExecutionEngine: Cancelling plan {plan_id}")
        with self._lock:
            plan = self.queue.get_plan(plan_id)
            if not plan:
                raise KeyError(f"Plan '{plan_id}' not found.")
            
            if plan_id in self._cancel_events:
                self._cancel_events[plan_id].set()
                
            plan.status = ExecutionState.CANCELLED
            for s in plan.steps:
                if s.status in ("pending", "executing", "paused"):
                    s.status = "cancelled"
            self._update_working_memory(plan)

    def _execute_plan_thread(self, plan_id: str) -> None:
        plan = self.queue.get_plan(plan_id)
        if not plan:
            return
            
        start_time = time.time()
        self.telemetry[plan_id] = {
            "start_time": start_time,
            "retries": 0,
            "errors": [],
            "success_rate": 100.0,
            "total_executed": 0,
            "total_success": 0
        }
        
        while True:
            if plan_id in self._cancel_events and self._cancel_events[plan_id].is_set():
                break
                
            with self._lock:
                if plan.status == ExecutionState.CANCELLED:
                    break
                if plan.status == ExecutionState.PAUSED:
                    time.sleep(0.5)
                    continue
                    
                next_step = self._get_next_runnable_step(plan)
                if not next_step:
                    non_terminal = [s for s in plan.steps if s.status in ("pending", "executing", "paused")]
                    if not non_terminal:
                        failed_steps = [s for s in plan.steps if s.status == "failed"]
                        if failed_steps:
                            plan.status = ExecutionState.FAILED
                        else:
                            plan.status = ExecutionState.COMPLETED
                        break
                    else:
                        time.sleep(0.2)
                        continue
                        
                next_step.status = "executing"
                self._update_working_memory(plan)
                
            self._execute_step(plan, next_step)
            
        with self._lock:
            self._threads.pop(plan_id, None)
            self._cancel_events.pop(plan_id, None)
            self._update_working_memory(plan)
            
            try:
                from nova.dashboard.event_bus import emit
                emit("task_completed", module="reasoning", status="success" if plan.status == ExecutionState.COMPLETED else "failed", metadata={
                    "plan_id": plan_id,
                    "status": plan.status,
                    "goal": plan.goal_description
                })
            except Exception:
                pass

    def _get_next_runnable_step(self, plan: Plan) -> Optional[PlanStep]:
        with self._lock:
            leaves = [s for s in plan.steps if not s.child_ids]
            terminal_ids = {s.id for s in plan.steps if s.status in ("completed", "skipped")}
            
            for s in leaves:
                if s.status == "pending":
                    deps_resolved = True
                    for dep_id in s.dependencies:
                        dep_step = next((x for x in plan.steps if x.id == dep_id), None)
                        if not dep_step:
                            continue
                        
                        if dep_step.child_ids:
                            descendants = self._get_leaf_descendants(plan, dep_step.id)
                            if not all(d_id in terminal_ids for d_id in descendants):
                                deps_resolved = False
                                break
                        else:
                            if dep_id not in terminal_ids:
                                deps_resolved = False
                                break
                                
                    if deps_resolved:
                        return s
            return None

    def _get_leaf_descendants(self, plan: Plan, step_id: str) -> List[str]:
        step = next((s for s in plan.steps if s.id == step_id), None)
        if not step:
            return []
        if not step.child_ids:
            return [step.id]
        leaves = []
        for c_id in step.child_ids:
            leaves.extend(self._get_leaf_descendants(plan, c_id))
        return leaves

    def _execute_step(self, plan: Plan, step: PlanStep) -> None:
        logger.info(f"ExecutionEngine: Executing step '{step.description}'")
        
        # ── Pre-step validation ──────────────────────────────────────
        
        # Browser safety check
        if "browser" in step.required_skills or step.action_type == "chromium_action":
            try:
                from nova.browser.manager import BrowserManager
                from nova.browser.helper import find_active_page
                
                if not BrowserManager.is_browser_running():
                    BrowserManager.ensure_browser()
                    
                browser = BrowserManager.get_browser()
                context = BrowserManager.get_persistent_context(browser)
                
                # Enforce safety: filter out chrome-extension:// pages
                pages = context.pages
                safe_pages = [p for p in pages if not (p.url or "").startswith("chrome-extension://")]
                
                if not safe_pages:
                    page = context.new_page()
                else:
                    page = find_active_page(context)
                    
                if (page.url or "").startswith("chrome-extension://"):
                    raise ValueError(f"Target URL points to an extension page: {page.url}")
            except Exception as e:
                self._handle_step_failure(plan, step, f"Browser Verification Failed: {e}")
                return

        # Filesystem safety check: verify parent directory for file operations
        structured_params = step.metadata.get("params", {})
        structured_action = step.metadata.get("action", "")
        if structured_action == "file_action" and structured_params.get("operation") == "create":
            import os
            file_path = structured_params.get("path", "")
            if file_path:
                parent = os.path.dirname(os.path.abspath(os.path.expanduser(file_path)))
                if not os.path.exists(parent):
                    logger.warning(f"Parent directory '{parent}' does not exist, will be created by file_action handler.")

        # ── Step execution via Action Engine routing ──────────────────
        
        success = False
        result_message = ""

        try:
            # PRIORITY 1: Structured action from metadata (new Structured Action Model)
            # Steps carry metadata.action and metadata.params for precise Action Engine routing.
            # Also handles flat NLP-style dicts: {"action": "volume_control", "operation": "increase", "level": 10}
            if structured_action and self.action_dispatcher and structured_action in self.action_dispatcher:
                handler = self.action_dispatcher[structured_action]
                if structured_params:
                    # Nested params style: {"action": "...", "params": {...}}
                    params = dict(structured_params)
                else:
                    # Flat NLP style: {"action": "...", "operation": "...", "level": 10, ...}
                    # Pass the whole metadata dict as params, excluding the "action" key itself.
                    params = {k: v for k, v in step.metadata.items() if k != "action"}
                params["_user_query"] = plan.goal_description
                result_message = handler.execute(params)
                success = "error" not in result_message.lower() and "failed" not in result_message.lower()
            
            # PRIORITY 2: action_type maps directly to a registered Action Engine handler
            elif self.action_dispatcher and step.action_type in self.action_dispatcher:
                handler = self.action_dispatcher[step.action_type]
                # Build params from structured metadata if available, else from legacy flat metadata
                if structured_params:
                    params = dict(structured_params)
                else:
                    params = {
                        "operation": step.metadata.get("operation") or "open",
                        "url": step.metadata.get("url") or step.expected_output,
                        "value": step.metadata.get("value") or step.description,
                        "query": step.metadata.get("query") or step.description,
                    }
                params["_user_query"] = plan.goal_description
                result_message = handler.execute(params)
                success = "error" not in result_message.lower() and "failed" not in result_message.lower()
            
            # PRIORITY 3: Command execution with proper argument lists (no raw shell strings)
            elif step.action_type == "command_execution":
                cmd = structured_params.get("command") or step.metadata.get("command")
                if not cmd:
                    result_message = f"Error: No command specified for command_execution step '{step.description}'."
                    success = False
                else:
                    # Ensure proper subprocess usage:
                    # - List → shell=False (safe, correct)
                    # - String → shell=True (needed for shell syntax)
                    use_shell = isinstance(cmd, str)
                    exit_code, stdout, stderr = CommandExecutor.run_shell(cmd, shell=use_shell, require_confirmation=False)
                    if exit_code == 0:
                        success = True
                        result_message = f"Command succeeded: {stdout.strip()}"
                    else:
                        success = False
                        result_message = f"Command failed (exit {exit_code}): {stderr.strip() or stdout.strip()}"

            # PRIORITY 4: generic_action handling
            # Parent/container steps (have child_ids) are coordinator nodes — auto-complete them.
            # Leaf steps may carry their real action inside metadata (flat or nested).
            elif step.action_type in ("generic_action", "generic"):
                if step.child_ids:
                    # This is a coordinator/phase parent — its children do the real work.
                    result_message = f"Phase '{step.description}' coordinator completed."
                    success = True
                else:
                    # Try to route by action name embedded directly in the step metadata.
                    # Handles cases where the planner stored action info as flat metadata keys.
                    meta_action = (
                        step.metadata.get("action")
                        or step.metadata.get("action_type")
                        or step.metadata.get("handler")
                    )
                    if meta_action and self.action_dispatcher and meta_action in self.action_dispatcher:
                        handler = self.action_dispatcher[meta_action]
                        params = dict(step.metadata)
                        params.setdefault("_user_query", plan.goal_description)
                        result_message = handler.execute(params)
                        success = "error" not in result_message.lower() and "failed" not in result_message.lower()
                    else:
                        # Truly unroutable leaf step — log a warning but do not hard-fail the plan.
                        result_message = f"Warning: Unroutable step '{step.description}' (action_type='{step.action_type}'). Skipping."
                        success = True  # Treat as skipped/no-op so the plan can continue.
                        logger.warning(result_message)

            # NO FALLBACK: Do not blindly run step.description as a shell command.
            else:
                result_message = f"Error: No action handler found for step '{step.description}' (action_type='{step.action_type}')."
                success = False
                logger.warning(result_message)

        except Exception as e:
            success = False
            result_message = f"Exception: {e}"

        if success:
            with self._lock:
                step.status = "completed"
                # Store the result message on the step object dynamically
                step.result_message = result_message
                self._record_timeline(plan, step.id, step.description, "completed")
                
                # Print output to sys.stdout in real-time so user can see it
                if result_message and not step.child_ids:
                    import sys
                    sys.stdout.write(result_message + "\n")
                    sys.stdout.flush()

                tel = self.telemetry.get(plan.id)
                if tel:
                    tel["total_executed"] += 1
                    tel["total_success"] += 1
                    tel["success_rate"] = (tel["total_success"] / tel["total_executed"]) * 100.0
                    
                self._propagate_parent_status(plan)
                self._update_working_memory(plan)
        else:
            self._handle_step_failure(plan, step, result_message)

    def _handle_step_failure(self, plan: Plan, step: PlanStep, error_msg: str) -> None:
        with self._lock:
            tel = self.telemetry.get(plan.id)
            if tel:
                tel["total_executed"] += 1
                tel["errors"].append(error_msg)
                tel["success_rate"] = (tel["total_success"] / tel["total_executed"]) * 100.0

            policy = step.recovery_policy or RecoveryPolicy()
            strategy = policy.strategy
            
            if strategy == "retry" and step.retry_count > 0:
                step.retry_count -= 1
                step.status = "pending"
                self._record_timeline(plan, step.id, step.description, "retry_triggered")
                if tel:
                    tel["retries"] += 1
            elif strategy == "skip":
                step.status = "skipped"
                self._record_timeline(plan, step.id, step.description, "skipped")
            elif strategy == "fallback_skill" and policy.fallback_skills:
                step.required_skills = list(policy.fallback_skills)
                step.required_skill = policy.fallback_skills[0]
                step.status = "pending"
                self._record_timeline(plan, step.id, step.description, "fallback_skill_applied")
            elif strategy == "alternative_step" and policy.alternative_step_desc:
                alt_id = str(uuid.uuid4())
                alt_step = PlanStep(
                    id=alt_id,
                    description=policy.alternative_step_desc,
                    action_type=policy.alternative_step_action or "generic",
                    required_skill="generic",
                    dependencies=list(step.dependencies),
                    status="pending",
                    parent_id=step.parent_id
                )
                alt_skills = determine_required_skills(alt_step.description, alt_step.action_type)
                alt_step.required_skills = alt_skills
                alt_step.required_skill = alt_skills[0] if alt_skills else "generic"
                plan.steps.append(alt_step)
                
                for s in plan.steps:
                    if step.id in s.dependencies:
                        s.dependencies = [alt_id if d == step.id else d for d in s.dependencies]
                
                step.status = "skipped"
                self._record_timeline(plan, step.id, step.description, "alternative_injected")
            elif strategy == "rollback":
                step.status = "failed"
                self._record_timeline(plan, step.id, step.description, "failed")
                plan.status = ExecutionState.FAILED
                
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
                    self._record_timeline(plan, rb_id, desc, "rollback_step_queued")
            elif strategy == "partial_completion" and policy.allow_partial:
                step.status = "skipped"
                self._record_timeline(plan, step.id, step.description, "partial_completion_allowed")
            else:
                step.status = "failed"
                self._record_timeline(plan, step.id, step.description, "failed")
                plan.status = ExecutionState.FAILED
                
            self._update_working_memory(plan)

    def _propagate_parent_status(self, plan: Plan) -> None:
        with self._lock:
            step_map = {s.id: s for s in plan.steps}
            parents = [s for s in plan.steps if s.child_ids]
            
            for p in parents:
                if p.status in ("pending", "executing", "paused"):
                    children = [step_map[cid] for cid in p.child_ids if cid in step_map]
                    if children and all(c.status in ("completed", "skipped") for c in children):
                        p.status = "completed"
                        self._record_timeline(plan, p.id, p.description, "completed")

    def _record_timeline(self, plan: Plan, step_id: str, step_desc: str, status: str) -> None:
        timeline = plan.metadata.setdefault("execution_timeline", [])
        timeline.append({
            "step_id": step_id,
            "description": step_desc,
            "status": status,
            "timestamp": time.time()
        })

    def _update_working_memory(self, plan: Plan) -> None:
        if self.working_memory and hasattr(self.working_memory, "set"):
            try:
                progress = self.get_progress(plan.id)
                self.working_memory.set("active_plan_progress", progress)
            except Exception as e:
                logger.error(f"Failed to update working memory: {e}")

    def get_progress(self, plan_id: str) -> Dict[str, Any]:
        with self._lock:
            plan = self.queue.get_plan(plan_id)
            if not plan:
                return {}
                
            completed = [s.id for s in plan.steps if s.status == "completed"]
            failed = [s.id for s in plan.steps if s.status == "failed"]
            running = [s.id for s in plan.steps if s.status == "executing"]
            waiting = [s.id for s in plan.steps if s.status in ("pending", "paused")]
            skipped = [s.id for s in plan.steps if s.status == "skipped"]
            
            leaves = [s for s in plan.steps if not s.child_ids]
            completed_leaves = [s for s in leaves if s.status == "completed"]
            skipped_leaves = [s for s in leaves if s.status == "skipped"]
            
            total_leaves = len(leaves)
            finished_leaves = len(completed_leaves) + len(skipped_leaves)
            completion_pct = (finished_leaves / total_leaves) * 100.0 if total_leaves > 0 else 0.0
            
            remaining_time = sum(s.timeout for s in leaves if s.status in ("pending", "executing", "paused"))
            
            tel = self.telemetry.get(plan_id, {})
            elapsed_time = time.time() - tel.get("start_time", time.time()) if plan.status == ExecutionState.RUNNING else 0.0
            
            current_step_desc = ""
            if running:
                curr_step = next((s for s in plan.steps if s.id == running[0]), None)
                if curr_step:
                    current_step_desc = curr_step.description
            
            progress_data = {
                "plan_id": plan_id,
                "goal": plan.goal_description,
                "status": plan.status,
                "current_step": current_step_desc,
                "total_steps": len(plan.steps),
                "completed_steps": completed,
                "failed_steps": failed,
                "running_steps": running,
                "waiting_steps": waiting,
                "skipped_steps": skipped,
                "completion_percentage": completion_pct,
                "estimated_remaining_time": remaining_time,
                "execution_time": elapsed_time,
                "retries": tel.get("retries", 0),
                "errors": list(dict.fromkeys(tel.get("errors", []))),
                "success_rate": tel.get("success_rate", 100.0),
                "execution_timeline": plan.metadata.get("execution_timeline", [])
            }
            return progress_data

def route_query_to_planner_pipeline(
    query: str,
    working_memory: Any,
    dispatcher: Any,
    approval_required: bool = True,
    actions: Optional[List[Dict[str, Any]]] = None
) -> str:
    """
    Standardized entry point mapping a user query to the Planner -> Validation -> Execution Engine flow.
    The optional `actions` parameter accepts a pre-parsed NLP actions list so the planner can
    route directly to the correct action handler instead of falling back to generic_action.
    """
    from nova.ai.planner import Planner, Goal
    from nova.utils import ask_confirmation, print_info, print_success, print_error, print_warning
    
    planner = Planner(working_memory=working_memory)
    exec_engine = ExecutionEngine(
        working_memory=working_memory,
        action_dispatcher=dispatcher,
        approval_required=approval_required
    )
    planner.execution_interface = exec_engine
    
    goal = Goal(description=query)
    # Attach pre-parsed NLP actions so the planner uses structured routing instead of generic_action
    if actions:
        goal.metadata = {"actions": actions}
    planning_result = planner.create_plan(goal)
    if not planning_result.success or not planning_result.plan:
        err_msg = f"Planning failed: {', '.join(planning_result.errors)}"
        print_error(err_msg)
        return err_msg
        
    plan = planning_result.plan
    
    validation_report = planner.validate_plan(plan)
    if not validation_report.valid:
        err_msg = f"Plan validation failed: {', '.join(validation_report.errors)}"
        print_error(err_msg)
        return err_msg
        
    exec_engine.submit_plan(plan)
    
    if plan.status == ExecutionState.WAITING_APPROVAL:
        # Build a detailed step display showing action routing
        step_lines = []
        leaf_steps = [s for s in plan.steps if not s.child_ids]
        for i, step in enumerate(leaf_steps):
            action = step.metadata.get("action", step.action_type)
            skills_str = ", ".join(step.required_skills) if step.required_skills else step.required_skill
            step_lines.append(f"  {i+1}. [{action}] {step.description}  (skills: {skills_str})")
        steps_str = "\n".join(step_lines)
        
        skills_str = ", ".join(plan.required_skills) if plan.required_skills else "generic"
        
        print_info(f"\n{'=' * 60}")
        print_info(f"  EXECUTION PLAN")
        print_info(f"{'=' * 60}")
        print_info(f"  Goal:       {plan.goal_description}")
        print_info(f"  Complexity: {plan.estimated_complexity}")
        print_info(f"  Duration:   {plan.estimated_duration:.1f}s estimated")
        print_info(f"  Skills:     {skills_str}")
        print_info(f"  Steps:      {len(leaf_steps)} executable steps")
        print_info(f"{'─' * 60}")
        print_info(f"{steps_str}")
        print_info(f"{'─' * 60}")
        print_info(f"  Status:     WAITING FOR APPROVAL")
        print_info(f"{'=' * 60}\n")
        
        approved = ask_confirmation("Would you like me to execute this plan?")
        if approved:
            exec_engine.approve_plan(plan.id)
        else:
            exec_engine.reject_plan(plan.id)
            return "Plan execution aborted by user."
    else:
        exec_engine.approve_plan(plan.id)
        
    print_info(f"Executing plan {plan.id}...")
    while True:
        progress = exec_engine.get_progress(plan.id)
        status = progress.get("status")
        
        if status in (ExecutionState.COMPLETED, ExecutionState.FAILED, ExecutionState.CANCELLED):
            if status == ExecutionState.COMPLETED:
                # Find the last completed leaf step's result_message
                result_msg = None
                for s in reversed(plan.steps):
                    if not s.child_ids and s.status == "completed" and hasattr(s, "result_message") and s.result_message:
                        result_msg = s.result_message
                        break

                msg = f"Plan execution completed successfully for goal '{plan.goal_description}'."
                print_success(msg)

                # Return the step's specific output result so CLI history and TTS get the correct string
                return result_msg if result_msg else msg
            elif status == ExecutionState.FAILED:
                errors = progress.get("errors", [])
                err_msg = f"Plan execution failed: {', '.join(errors)}"
                print_error(err_msg)
                return err_msg
            else:
                msg = "Plan execution was cancelled."
                print_warning(msg)
                return msg
                
        time.sleep(0.5)
