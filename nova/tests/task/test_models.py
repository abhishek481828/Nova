"""
Unit tests for task data models.
"""
import unittest
from nova.task.models import Task, TaskStep, TaskStatus, TaskReport

class TestTaskModels(unittest.TestCase):
    def test_task_status_enum(self):
        self.assertEqual(TaskStatus.PENDING, "pending")
        self.assertEqual(TaskStatus.RUNNING, "running")
        self.assertEqual(TaskStatus.COMPLETED, "completed")
        self.assertEqual(TaskStatus.FAILED, "failed")

    def test_task_step_instantiation(self):
        step = TaskStep(
            description="Setup project",
            action_type="create_file",
            timeout=30.0
        )
        self.assertIsNotNone(step.id)
        self.assertEqual(step.status, TaskStatus.PENDING)
        self.assertEqual(step.timeout, 30.0)
        self.assertEqual(len(step.files_created), 0)

    def test_task_instantiation(self):
        task = Task(goal_description="Build JWT Auth")
        self.assertIsNotNone(task.id)
        self.assertEqual(task.status, TaskStatus.PENDING)
        self.assertEqual(len(task.steps), 0)
        self.assertEqual(len(task.rollbacks_executed), 0)

    def test_task_report_compilation(self):
        report = TaskReport(
            task_id="task-123",
            goal="Add configuration",
            status=TaskStatus.COMPLETED,
            steps_executed=2,
            steps_completed=2,
            steps_failed=0,
            files_created=["config.json"],
            files_modified=["main.py"],
            rollbacks=[],
            total_execution_time_s=12.5,
            validation_status=True,
            validation_errors=[],
            metadata={"priority": "high"}
        )
        self.assertTrue(report.validation_status)
        self.assertEqual(report.status, TaskStatus.COMPLETED)
        self.assertEqual(report.files_created, ["config.json"])
