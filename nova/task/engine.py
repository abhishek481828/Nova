"""
nova.task.engine
~~~~~~~~~~~~~~~~
TaskExecutionEngine — coordinates goal decomposition, sequential execution,
post-step verification, scoped rollback, progress reporting, and state management.
"""
from __future__ import annotations

import logging
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

from nova.ai.planner.planner import Planner
from nova.ai.planner.models import Goal, PlanStep, Plan
from nova.browser.providers.chatgpt import ChatGPTProvider
from nova.edit import get_code_editor
from nova.task.models import Task, TaskStep, TaskStatus, TaskReport
from nova.task.executor import StepExecutor
from nova.task.verification import StepVerifier

logger = logging.getLogger("nova.task.engine")


class TaskExecutionEngine:
    """
    Orchestrator for autonomous software development task execution.
    Thread-safe singleton.
    """

    _instance: Optional["TaskExecutionEngine"] = None
    _instance_lock = threading.Lock()

    def __new__(cls) -> "TaskExecutionEngine":
        with cls._instance_lock:
            if cls._instance is None:
                obj = super().__new__(cls)
                obj._initialised = False
                cls._instance = obj
            return cls._instance

    def __init__(self) -> None:
        if self._initialised:
            return
        self.active_tasks: Dict[str, Task] = {}
        self._lock = threading.RLock()
        self._threads: Dict[str, threading.Thread] = {}
        self._cancel_events: Dict[str, threading.Event] = {}
        self._pause_events: Dict[str, threading.Event] = {}
        self.confirm_callback: Optional[Callable[[str], bool]] = None
        # Observer hooks — set by DevelopmentSessionManager or any external listener.
        # Signature: (task: Task, step: TaskStep) -> None
        self.on_step_complete: Optional[Callable] = None
        self.on_step_failed: Optional[Callable] = None
        self._initialised = True

    def _get_project_root(self) -> Path:
        try:
            from nova.project.engine import ProjectAwarenessEngine
            ctx = ProjectAwarenessEngine().get_context()
            if ctx:
                return ctx.root
        except Exception:
            pass
        return Path.cwd()

    # ── Public API ──────────────────────────────────────────────────

    def create_task(self, goal_description: str, priority: str = "medium") -> Task:
        """
        Create a new Task. Translates high-level goal into TaskSteps
        using Planner template match or fallback AI Provider planning.
        """
        task_id = str(time.time()) # simple timestamp-based ID
        task = Task(id=task_id, goal_description=goal_description)
        
        # 1. Try mapping via standard template
        planner = Planner()
        template = planner.match_template(goal_description)
        steps_list: List[TaskStep] = []
        
        if template:
            proj_name = planner.determine_project_name(goal_description, template)
            details = planner._get_template_details(template, proj_name)
            # Create a mock Plan root step to generate hierarchical steps
            root_id = str(uuid.uuid4()) if 'uuid' in globals() else "root"
            p_steps = planner._generate_hierarchical_steps(details, priority, root_id)
            
            # Map PlanSteps to TaskSteps
            for ps in p_steps:
                # We skip parent steps that represent phases and only include execution leaf steps
                if ps.child_ids:
                    continue
                step = TaskStep(
                    id=ps.id,
                    description=ps.description,
                    action_type=ps.action_type,
                    dependencies=list(ps.dependencies),
                    expected_artifact=ps.expected_artifact,
                    metadata=dict(ps.metadata)
                )
                steps_list.append(step)
        else:
            # 2. Fallback: Ask AIProvider to decompose the task into steps
            steps_list = self._decompose_goal_via_ai(goal_description)

        task.steps = steps_list
        with self._lock:
            self.active_tasks[task.id] = task
        
        logger.info(f"[TaskEngine] Created task {task.id} with {len(task.steps)} steps for goal: {goal_description}")
        return task

    def execute_task(self, task_id: str, run_test_suite: bool = False, test_command: Optional[str] = None) -> None:
        """
        Execute the task in a background daemon thread.
        """
        with self._lock:
            task = self.active_tasks.get(task_id)
            if not task:
                raise KeyError(f"Task with ID {task_id} not found.")
            
            if task.status in (TaskStatus.RUNNING, TaskStatus.COMPLETED):
                return
                
            task.status = TaskStatus.RUNNING
            cancel_event = threading.Event()
            pause_event = threading.Event()
            self._cancel_events[task_id] = cancel_event
            self._pause_events[task_id] = pause_event
            
        t = threading.Thread(
            target=self._run_task_thread,
            args=(task, cancel_event, pause_event, run_test_suite, test_command),
            name=f"TaskRunner-{task_id}",
            daemon=True
        )
        with self._lock:
            self._threads[task_id] = t
        t.start()
        logger.info(f"[TaskEngine] Started task execution thread for {task_id}")

    def pause_task(self, task_id: str) -> None:
        with self._lock:
            task = self.active_tasks.get(task_id)
            pe = self._pause_events.get(task_id)
            if not task or not pe:
                return
            pe.set()
            task.status = TaskStatus.PAUSED
            logger.info(f"[TaskEngine] Paused task {task_id}")

    def resume_task(self, task_id: str) -> None:
        with self._lock:
            task = self.active_tasks.get(task_id)
            pe = self._pause_events.get(task_id)
            if not task or not pe:
                return
            pe.clear()
            task.status = TaskStatus.RUNNING
            logger.info(f"[TaskEngine] Resumed task {task_id}")

    def cancel_task(self, task_id: str) -> None:
        with self._lock:
            task = self.active_tasks.get(task_id)
            ce = self._cancel_events.get(task_id)
            if not task or not ce:
                return
            ce.set()
            task.status = TaskStatus.CANCELLED
            logger.info(f"[TaskEngine] Cancelled task {task_id}")

    def get_task_status(self, task_id: str) -> TaskStatus:
        with self._lock:
            task = self.active_tasks.get(task_id)
            if not task:
                raise KeyError(f"Task with ID {task_id} not found.")
            return task.status

    def get_task_report(self, task_id: str) -> Optional[TaskReport]:
        with self._lock:
            task = self.active_tasks.get(task_id)
        if not task:
            return None

        # Gather created/modified files
        created = []
        modified = []
        steps_executed = 0
        steps_completed = 0
        steps_failed = 0

        for step in task.steps:
            if step.status != TaskStatus.PENDING:
                steps_executed += 1
            if step.status == TaskStatus.COMPLETED:
                steps_completed += 1
                created.extend(step.files_created)
                modified.extend(step.files_modified)
            elif step.status == TaskStatus.FAILED:
                steps_failed += 1

        # Check syntax validation of resulting files
        root = self._get_project_root()
        verifier = StepVerifier(root)
        val_status, val_errors = verifier.verify_syntax(created + modified)

        return TaskReport(
            task_id=task.id,
            goal=task.goal_description,
            status=task.status,
            steps_executed=steps_executed,
            steps_completed=steps_completed,
            steps_failed=steps_failed,
            files_created=list(set(created)),
            files_modified=list(set(modified)),
            rollbacks=list(task.rollbacks_executed),
            total_execution_time_s=task.duration_s,
            validation_status=val_status,
            validation_errors=val_errors,
            metadata=dict(task.metadata)
        )

    # ── Internal Task Runner ──────────────────────────────────────

    def _decompose_goal_via_ai(self, goal: str) -> List[TaskStep]:
        """
        Queries ChatGPTProvider to decompose a generic goal into TaskSteps.
        """
        prompt = (
            f"Decompose the following coding goal into sequential, executable steps:\n"
            f"Goal: {goal}\n\n"
            f"Provide the plan in JSON list format where each item contains:\n"
            f" - 'description': short explanation of step\n"
            f" - 'action_type': one of ('create_file', 'update_file', 'rename_symbol', 'delete_file', 'run_command', 'generic')\n"
            f" - 'metadata': dict with 'rel_path' or 'command' as needed\n"
            f"Example:\n"
            f"[{{\"description\": \"Create db.py\", \"action_type\": \"create_file\", \"metadata\": {{\"rel_path\": \"db.py\"}}}}]\n"
            f"Output JSON ONLY."
        )

        try:
            resp = ChatGPTProvider.execute_action("ask", prompt)
            import json
            # Extract JSON array
            match = re.search(r"\[.*\]", resp, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
            else:
                data = json.loads(resp)
                
            steps = []
            for item in data:
                steps.append(TaskStep(
                    description=item.get("description", ""),
                    action_type=item.get("action_type", "generic"),
                    metadata=item.get("metadata", {})
                ))
            return steps
        except Exception as e:
            logger.warning(f"Decomposition failed: {e}. Generating single fallback step.")
            # Fallback single step
            return [TaskStep(
                description=f"Implement goal: {goal}",
                action_type="generic",
                metadata={"rel_path": "main.py"}
            )]

    def _run_task_thread(
        self,
        task: Task,
        cancel_event: threading.Event,
        pause_event: threading.Event,
        run_test_suite: bool,
        test_command: Optional[str]
    ) -> None:
        t0 = time.perf_counter()
        root = self._get_project_root()
        executor = StepExecutor(root, self.confirm_callback)
        verifier = StepVerifier(root)
        editor = get_code_editor()

        logger.info(f"[TaskEngine] Starting execution loop for task {task.id}")
        
        try:
            for step in task.steps:
                # 1. Check for cancel request
                if cancel_event.is_set():
                    task.status = TaskStatus.CANCELLED
                    break

                # 2. Check for pause request
                while pause_event.is_set():
                    if cancel_event.is_set():
                        task.status = TaskStatus.CANCELLED
                        break
                    time.sleep(0.5)

                if task.status == TaskStatus.CANCELLED:
                    break

                step.status = TaskStatus.RUNNING
                logger.info(f"[TaskEngine] Executing step: {step.description}")
                
                # Measure pre-step editor history length for potential scoped rollback
                pre_step_history_len = len(editor.history)
                step_start_time = time.perf_counter()
                
                step_success = False
                
                # Retry Loop
                for attempt in range(step.retry_count):
                    # Pause/cancel check in retry loop
                    if cancel_event.is_set():
                        break

                    if attempt > 0:
                        step.status = TaskStatus.RETRYING
                        logger.info(f"[TaskEngine] Retrying step: {step.description} (attempt {attempt+1}/{step.retry_count})")

                    # Execute the modification
                    ok, created, modified, err = executor.execute_step(
                        step.description,
                        step.action_type,
                        step.metadata
                    )
                    
                    if ok:
                        # Perform syntactical and logical verification
                        verified, ver_errors = verifier.verify_step(
                            created,
                            modified,
                            run_test_suite=run_test_suite,
                            test_command=test_command
                        )
                        if verified:
                            step.files_created = created
                            step.files_modified = modified
                            step_success = True
                            break
                        else:
                            step.error_message = f"Verification failed: {ver_errors[0]}"
                    else:
                        step.error_message = err

                    # If attempt failed, execute step-level rollback before retrying
                    self._rollback_to_checkpoint(editor, pre_step_history_len)

                # Final step outcome
                step.duration_s = time.perf_counter() - step_start_time
                if step_success:
                    step.status = TaskStatus.COMPLETED
                    logger.info(f"[TaskEngine] Step completed: {step.description}")
                    if self.on_step_complete:
                        try:
                            self.on_step_complete(task, step)
                        except Exception:
                            pass
                else:
                    step.status = TaskStatus.FAILED
                    # Record step rollback audit trail
                    task.rollbacks_executed.append(step.description)
                    logger.error(f"[TaskEngine] Step failed: {step.description} - Error: {step.error_message}")
                    if self.on_step_failed:
                        try:
                            self.on_step_failed(task, step)
                        except Exception:
                            pass
                    task.status = TaskStatus.FAILED
                    break

            else:
                # Loop completed without breaking (or hitting a failed step)
                task.status = TaskStatus.COMPLETED
                logger.info(f"[TaskEngine] Task completed successfully: {task.id}")

        except Exception as e:
            logger.error(f"[TaskEngine] Error during task loop: {e}", exc_info=True)
            task.status = TaskStatus.FAILED
            
        finally:
            task.finished_at = time.time()
            task.duration_s = round(time.perf_counter() - t0, 3)
            self._emit_dashboard_event(task)

    def _rollback_to_checkpoint(self, editor, checkpoint_len: int) -> None:
        """Roll back only the edits applied since the checkpoint length."""
        while len(editor.history) > checkpoint_len:
            editor.rollback_last_change()

    def _emit_dashboard_event(self, task: Task) -> None:
        try:
            from nova.dashboard.event_bus import emit
            emit(
                "task_finished",
                module="task_execution",
                status="success" if task.status == TaskStatus.COMPLETED else "failed",
                metadata={
                    "task_id": task.id,
                    "goal": task.goal_description,
                    "status": task.status.value,
                    "duration_s": task.duration_s
                }
            )
        except Exception:
            pass
