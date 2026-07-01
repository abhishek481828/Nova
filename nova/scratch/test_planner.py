import unittest
import json
from nova.planner import Planner, Goal, PlanStep, Plan, PlanningContext

class TestPlanner(unittest.TestCase):
    def setUp(self):
        self.planner = Planner()

    def test_simple_goal_generation(self):
        goal = Goal(description="Run system specs update", priority="low")
        result = self.planner.create_plan(goal)
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.plan)
        self.assertEqual(len(result.plan.steps), 1)
        self.assertEqual(result.plan.priority, "low")
        self.assertEqual(result.plan.steps[0].action_type, "generic_action")

    def test_multi_step_goal_generation(self):
        goal = Goal(description="open chrome and search youtube videos", priority="high")
        result = self.planner.create_plan(goal)
        
        self.assertTrue(result.success)
        self.assertIsNotNone(result.plan)
        self.assertEqual(len(result.plan.steps), 3)
        self.assertEqual(result.plan.steps[1].action_type, "chromium_action")
        self.assertEqual(result.plan.steps[2].action_type, "chromium_action")
        self.assertIn(result.plan.steps[1].id, result.plan.steps[2].dependencies)

    def test_invalid_goals(self):
        # 1. Empty goal validation
        goal = Goal(description="   ")
        result = self.planner.create_plan(goal)
        self.assertFalse(result.success)
        self.assertIn("Goal description cannot be empty.", result.errors)

        # 2. Priority validation
        with self.assertRaises(ValueError):
            Goal(description="Valid description", priority="invalid_priority").validate()

    def test_unresolved_dependencies(self):
        # Create plan with step depending on non-existent step id
        goal = Goal(description="Dependency check")
        step1 = PlanStep(description="Step 1", dependencies=["non-existent-id"])
        plan = Plan(goal=goal, steps=[step1])
        
        valid, errors = self.planner.validate_plan(plan)
        self.assertFalse(valid)
        self.assertTrue(any("unresolved dependency" in err for err in errors))

    def test_cyclic_dependencies(self):
        # A -> B -> A
        goal = Goal(description="Cycle check")
        stepA = PlanStep(id="A", description="Step A", dependencies=["B"])
        stepB = PlanStep(id="B", description="Step B", dependencies=["A"])
        plan = Plan(goal=goal, steps=[stepA, stepB])
        
        valid, errors = self.planner.validate_plan(plan)
        self.assertFalse(valid)
        self.assertIn("Dependency cycle detected in plan steps.", errors)

        # A -> B -> C -> A
        stepC = PlanStep(id="C", description="Step C", dependencies=["A"])
        stepB_longer = PlanStep(id="B", description="Step B", dependencies=["C"])
        plan_longer = Plan(goal=goal, steps=[stepA, stepB_longer, stepC])
        
        valid_longer, errors_longer = self.planner.validate_plan(plan_longer)
        self.assertFalse(valid_longer)
        self.assertIn("Dependency cycle detected in plan steps.", errors_longer)

    def test_plan_export_and_import(self):
        goal = Goal(description="git pull and run tests")
        result = self.planner.create_plan(goal)
        self.assertTrue(result.success)
        
        # Export to JSON
        exported_json = self.planner.export_plan(result.plan)
        self.assertIsNotNone(exported_json)
        
        # Import back
        imported_plan = self.planner.import_plan(exported_json)
        self.assertEqual(imported_plan.id, result.plan.id)
        self.assertEqual(imported_plan.goal.description, result.plan.goal.description)
        self.assertEqual(len(imported_plan.steps), len(result.plan.steps))
        self.assertEqual(imported_plan.steps[1].dependencies, result.plan.steps[1].dependencies)

    def test_cancel_plan(self):
        goal = Goal(description="simple goal")
        result = self.planner.create_plan(goal)
        self.assertTrue(result.success)
        
        plan = result.plan
        self.assertEqual(plan.status, "validated")
        
        cancelled_plan = self.planner.cancel_plan(plan)
        self.assertEqual(cancelled_plan.status, "cancelled")
        self.assertEqual(cancelled_plan.steps[0].status, "cancelled")

if __name__ == "__main__":
    unittest.main()
