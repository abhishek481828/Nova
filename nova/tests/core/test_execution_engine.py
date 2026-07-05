import sys
from unittest.mock import MagicMock

import unittest
import time
import uuid
import threading
from unittest.mock import patch
from typing import Dict, Any, List, Optional

from nova.ai.planner import Planner, Goal, Plan, PlanStep, RecoveryPolicy
from nova.ai.reasoning import ExecutionEngine, ExecutionState, PlanQueue
from nova.core.memory import WorkingMemory
from nova.core.memory import LongTermMemoryManager
from nova.actions.base import BaseAction

class MockMemory:
    def __init__(self, content: str, category: str):
        self.content = content
        self.category = category

class MockLTMManager:
    def __init__(self, memories: List[MockMemory]):
        self.memories = memories
    def list_memories(self, category: Optional[str] = None) -> List[MockMemory]:
        return [m for m in self.memories if not category or m.category == category]

class MockAction(BaseAction):
    def __init__(self, name: str, behavior="success"):
        self._name = name
        self.behavior = behavior
        self.called_count = 0

    @property
    def action_name(self) -> str:
        return self._name

    def execute(self, params: Dict[str, Any]) -> str:
        self.called_count += 1
        if self.behavior == "success":
            return "success"
        elif self.behavior == "fail":
            return "error: mock execution failed"
        else:
            return "aborted"

class TestExecutionEngine(unittest.TestCase):
    def setUp(self):
        self.wm = WorkingMemory()
        self.dispatcher = {
            "mock_success": MockAction("mock_success", "success"),
            "mock_fail": MockAction("mock_fail", "fail"),
            "mock_abort": MockAction("mock_abort", "abort"),
            "chromium_action": MockAction("chromium_action", "success")
        }
        self.engine = ExecutionEngine(
            working_memory=self.wm,
            action_dispatcher=self.dispatcher,
            approval_required=True
        )

    def test_simple_plan_execution(self):
        # Enforce manual approval configuration
        plan = Plan(id="p1", goal_description="Test Goal")
        step = PlanStep(
            id="s1",
            description="Run command success",
            action_type="mock_success",
            required_skills=["system"]
        )
        plan.steps.append(step)
        
        self.engine.submit_plan(plan)
        self.assertEqual(plan.status, ExecutionState.WAITING_APPROVAL)
        
        # Approve execution
        self.engine.approve_plan(plan.id)
        
        # Wait for completion
        start = time.time()
        while plan.status not in (ExecutionState.COMPLETED, ExecutionState.FAILED):
            time.sleep(0.05)
            if time.time() - start > 2.0:
                self.fail("Plan execution timed out")
                
        self.assertEqual(plan.status, ExecutionState.COMPLETED)
        self.assertEqual(step.status, "completed")
        self.assertEqual(self.dispatcher["mock_success"].called_count, 1)

    def test_multi_step_sequencing(self):
        plan = Plan(id="p2", goal_description="Multi Goal")
        s1 = PlanStep(id="s1", description="Step 1", action_type="mock_success")
        s2 = PlanStep(id="s2", description="Step 2", action_type="mock_success", dependencies=["s1"])
        plan.steps.extend([s1, s2])
        
        self.engine.approval_required = False
        self.engine.submit_plan(plan)
        self.engine.approve_plan(plan.id)
        
        start = time.time()
        while plan.status != ExecutionState.COMPLETED:
            time.sleep(0.05)
            if time.time() - start > 2.0:
                self.fail("Plan execution timed out")
                
        self.assertEqual(s1.status, "completed")
        self.assertEqual(s2.status, "completed")

    def test_pause_resume_cancel(self):
        plan = Plan(id="p3", goal_description="Control Goal")
        s1 = PlanStep(id="s1", description="Step 1", action_type="mock_success")
        s2 = PlanStep(id="s2", description="Step 2", action_type="mock_success", dependencies=["s1"])
        plan.steps.extend([s1, s2])
        
        self.engine.approval_required = False
        self.engine.submit_plan(plan)
        
        # Start and pause immediately
        self.engine.approve_plan(plan.id)
        self.engine.pause_plan(plan.id)
        self.assertEqual(plan.status, ExecutionState.PAUSED)
        
        # Resume
        self.engine.resume_plan(plan.id)
        self.assertEqual(plan.status, ExecutionState.RUNNING)
        
        # Cancel
        self.engine.cancel_plan(plan.id)
        self.assertEqual(plan.status, ExecutionState.CANCELLED)

    def test_recovery_policy_retry(self):
        plan = Plan(id="p4", goal_description="Retry Goal")
        policy = RecoveryPolicy(strategy="retry", max_retries=2)
        step = PlanStep(
            id="s1",
            description="Step failing",
            action_type="mock_fail",
            retry_count=2,
            recovery_policy=policy
        )
        plan.steps.append(step)
        
        self.engine.approval_required = False
        self.engine.submit_plan(plan)
        self.engine.approve_plan(plan.id)
        
        start = time.time()
        while plan.status not in (ExecutionState.COMPLETED, ExecutionState.FAILED):
            time.sleep(0.05)
            if time.time() - start > 2.0:
                self.fail("Plan execution timed out")
                
        self.assertEqual(plan.status, ExecutionState.FAILED)
        self.assertEqual(self.dispatcher["mock_fail"].called_count, 3) # Init + 2 retries

    def test_recovery_policy_skip(self):
        plan = Plan(id="p5", goal_description="Skip Goal")
        policy = RecoveryPolicy(strategy="skip")
        s1 = PlanStep(id="s1", description="Failing step", action_type="mock_fail", recovery_policy=policy)
        s2 = PlanStep(id="s2", description="Next step", action_type="mock_success", dependencies=["s1"])
        plan.steps.extend([s1, s2])
        
        self.engine.approval_required = False
        self.engine.submit_plan(plan)
        self.engine.approve_plan(plan.id)
        
        start = time.time()
        while plan.status not in (ExecutionState.COMPLETED, ExecutionState.FAILED):
            time.sleep(0.05)
            if time.time() - start > 2.0:
                self.fail("Plan execution timed out")
                
        self.assertEqual(plan.status, ExecutionState.COMPLETED)
        self.assertEqual(s1.status, "skipped")
        self.assertEqual(s2.status, "completed")

    @patch("nova.browser.helper.find_active_page")
    @patch("nova.browser.manager.BrowserManager.is_browser_running")
    @patch("nova.browser.manager.BrowserManager.get_browser")
    @patch("nova.browser.manager.BrowserManager.get_persistent_context")
    def test_browser_state_checks(self, mock_get_context, mock_get_browser, mock_is_running, mock_find_active):
        # Setup mocks to avoid launching real Playwright Chromium
        mock_is_running.return_value = True
        mock_context = MagicMock()
        mock_page = MagicMock()
        mock_page.url = "https://example.com"
        mock_context.pages = [mock_page]
        mock_get_context.return_value = mock_context
        
        # Setup mock for find_active_page
        mock_active_page = MagicMock()
        mock_active_page.url = "https://example.com"
        mock_find_active.return_value = mock_active_page
        
        plan = Plan(id="p_browser", goal_description="Browser Goal")
        step = PlanStep(
            id="s1",
            description="Open URL example",
            action_type="chromium_action",
            required_skills=["browser"],
            metadata={"operation": "open", "url": "https://example.com"}
        )
        plan.steps.append(step)
        
        self.engine.approval_required = False
        self.engine.submit_plan(plan)
        self.engine.approve_plan(plan.id)
        
        start = time.time()
        while plan.status not in (ExecutionState.COMPLETED, ExecutionState.FAILED):
            time.sleep(0.05)
            if time.time() - start > 2.0:
                self.fail("Plan execution timed out")
                
        if plan.status != ExecutionState.COMPLETED:
            print("BROWSER TEST ERROR TELEMETRY:", self.engine.telemetry.get(plan.id))
            print("BROWSER TEST ERROR TIMELINE:", plan.metadata.get("execution_timeline"))
        self.assertEqual(plan.status, ExecutionState.COMPLETED)

    def test_working_memory_updates(self):
        plan = Plan(id="p_wm", goal_description="WM Goal")
        step = PlanStep(id="s1", description="Step 1", action_type="mock_success")
        plan.steps.append(step)
        
        self.engine.approval_required = False
        self.engine.submit_plan(plan)
        self.engine.approve_plan(plan.id)
        
        start = time.time()
        while plan.status != ExecutionState.COMPLETED:
            time.sleep(0.05)
            if time.time() - start > 2.0:
                self.fail("Plan execution timed out")
                
        progress = self.wm.get("active_plan_progress")
        self.assertIsNotNone(progress)
        self.assertEqual(progress.get("status"), ExecutionState.COMPLETED)
        self.assertEqual(progress.get("completion_percentage"), 100.0)

    def test_ltm_integration_read_only(self):
        mock_mem = MockMemory(content="preferred browser is Chromium", category="preferences")
        mock_ltm = MockLTMManager([mock_mem])
        
        planner = Planner(working_memory=self.wm, ltm_manager=mock_ltm)
        goal = Goal(description="open browser")
        
        plan_result = planner.create_plan(goal)
        self.assertTrue(plan_result.success)
        # Verify preferred browser read from LTM was applied to description
        self.assertIn("Chromium", plan_result.plan.steps[0].description)

    def test_concurrent_plan_execution(self):
        plans = []
        for i in range(3):
            p = Plan(id=f"p_concurrent_{i}", goal_description=f"Concurrent Goal {i}")
            s = PlanStep(id=f"s_{i}", description="Step", action_type="mock_success")
            p.steps.append(s)
            plans.append(p)
            
        self.engine.approval_required = False
        
        # Submit and approve all
        for p in plans:
            self.engine.submit_plan(p)
            self.engine.approve_plan(p.id)
            
        # Wait for all to finish
        start = time.time()
        while not all(p.status == ExecutionState.COMPLETED for p in plans):
            time.sleep(0.05)
            if time.time() - start > 3.0:
                self.fail("Concurrent executions timed out or deadlocked")
                
        for p in plans:
            self.assertEqual(p.status, ExecutionState.COMPLETED)
    def test_structured_action_routing_via_metadata(self):
        """Steps with metadata.action should route through the matching dispatcher handler."""
        # Register a file_action mock
        self.dispatcher["file_action"] = MockAction("file_action", "success")
        
        plan = Plan(id="p_struct", goal_description="Create Directory")
        step = PlanStep(
            id="s1",
            description="Create project directory",
            action_type="file_action",
            required_skills=["files"],
            metadata={
                "action": "file_action",
                "params": {"operation": "create_directory", "path": "flask_project"}
            }
        )
        plan.steps.append(step)
        
        self.engine.approval_required = False
        self.engine.submit_plan(plan)
        self.engine.approve_plan(plan.id)
        
        start = time.time()
        while plan.status not in (ExecutionState.COMPLETED, ExecutionState.FAILED):
            time.sleep(0.05)
            if time.time() - start > 2.0:
                self.fail("Plan execution timed out")
                
        self.assertEqual(plan.status, ExecutionState.COMPLETED)
        self.assertEqual(step.status, "completed")
        # Verify the file_action handler was called, not a shell command
        self.assertEqual(self.dispatcher["file_action"].called_count, 1)

    def test_no_shell_fallback_for_unknown_action_type(self):
        """Steps with unrecognized action_type should NOT fall back to shell execution."""
        plan = Plan(id="p_noshell", goal_description="No Shell")
        step = PlanStep(
            id="s1",
            description="rm -rf /",  # This should NEVER be run as a shell command
            action_type="unknown_action",
            required_skills=["system"],
            metadata={}
        )
        plan.steps.append(step)
        
        self.engine.approval_required = False
        self.engine.submit_plan(plan)
        self.engine.approve_plan(plan.id)
        
        start = time.time()
        while plan.status not in (ExecutionState.COMPLETED, ExecutionState.FAILED):
            time.sleep(0.05)
            if time.time() - start > 2.0:
                self.fail("Plan execution timed out")
                
        # Should FAIL because no handler exists — NOT succeed by running as shell
        self.assertEqual(plan.status, ExecutionState.FAILED)
        self.assertEqual(step.status, "failed")

    def test_command_execution_with_list_args(self):
        """command_execution steps with list commands should use shell=False (safe mode)."""
        plan = Plan(id="p_cmd", goal_description="Command Test")
        step = PlanStep(
            id="s1",
            description="Run echo test",
            action_type="command_execution",
            required_skills=["system"],
            metadata={
                "action": "command_execution",
                "params": {"command": ["echo", "hello"]}
            }
        )
        plan.steps.append(step)
        
        self.engine.approval_required = False
        self.engine.submit_plan(plan)
        self.engine.approve_plan(plan.id)
        
        start = time.time()
        while plan.status not in (ExecutionState.COMPLETED, ExecutionState.FAILED):
            time.sleep(0.05)
            if time.time() - start > 2.0:
                self.fail("Plan execution timed out")
                
        self.assertEqual(plan.status, ExecutionState.COMPLETED)
        self.assertEqual(step.status, "completed")

    def test_approval_required_by_default(self):
        """Plans should enter WAITING_APPROVAL state when approval_required=True (the default)."""
        engine = ExecutionEngine(
            working_memory=self.wm,
            action_dispatcher=self.dispatcher,
            approval_required=True
        )
        
        plan = Plan(id="p_approval", goal_description="Approval Test")
        step = PlanStep(id="s1", description="Step 1", action_type="mock_success")
        plan.steps.append(step)
        
        engine.submit_plan(plan)
        
        # Plan should be waiting, NOT running
        self.assertEqual(plan.status, ExecutionState.WAITING_APPROVAL)
        
        # Reject the plan
        engine.reject_plan(plan.id)
        self.assertEqual(plan.status, ExecutionState.CANCELLED)
        self.assertEqual(step.status, "cancelled")

    def test_metadata_action_priority_over_action_type(self):
        """When metadata.action differs from action_type, metadata.action takes priority."""
        # Register handlers
        self.dispatcher["file_action"] = MockAction("file_action", "success")
        self.dispatcher["generic_action"] = MockAction("generic_action", "fail")
        
        plan = Plan(id="p_priority", goal_description="Priority Test")
        step = PlanStep(
            id="s1",
            description="Create file",
            action_type="generic_action",  # This should NOT be used
            metadata={
                "action": "file_action",  # This SHOULD be used
                "params": {"operation": "create", "path": "/tmp/test.txt", "content": "hello"}
            }
        )
        plan.steps.append(step)
        
        self.engine.approval_required = False
        self.engine.submit_plan(plan)
        self.engine.approve_plan(plan.id)
        
        start = time.time()
        while plan.status not in (ExecutionState.COMPLETED, ExecutionState.FAILED):
            time.sleep(0.05)
            if time.time() - start > 2.0:
                self.fail("Plan execution timed out")
        
        # file_action handler was used (success), NOT generic_action (which would fail)
        self.assertEqual(plan.status, ExecutionState.COMPLETED)
        self.assertEqual(self.dispatcher["file_action"].called_count, 1)
        self.assertEqual(self.dispatcher["generic_action"].called_count, 0)

    def test_execution_errors_deduplication(self):
        """Identical execution errors in get_progress should be deduplicated."""
        plan = Plan(id="p_dedup", goal_description="Dedup Test")
        step = PlanStep(
            id="s1",
            description="Failing step",
            action_type="mock_fail",
        )
        plan.steps.append(step)
        
        self.engine.submit_plan(plan)
        # Initialize telemetry entry
        self.engine.telemetry[plan.id] = {
            "start_time": 0.0,
            "retries": 0,
            "errors": [],
            "success_rate": 100.0,
            "total_executed": 0,
            "total_success": 0
        }
        # Record step failure twice with identical message
        self.engine._handle_step_failure(plan, step, "Access denied")
        self.engine._handle_step_failure(plan, step, "Access denied")
        
        progress = self.engine.get_progress(plan.id)
        self.assertEqual(progress.get("errors"), ["Access denied"])

if __name__ == "__main__":
    unittest.main()
