import unittest
import os
import tempfile
import shutil
from nova.ai.planner import Planner, Goal, PlanStep, Plan, PlanningContext

class TestPlanningIntelligence(unittest.TestCase):
    def setUp(self):
        self.planner = Planner()
        self.temp_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.temp_dir)

    def test_flask_website_template(self):
        goal = Goal(description="Build a Flask website", priority="high")
        result = self.planner.create_plan(goal)
        
        self.assertTrue(result.success)
        plan = result.plan
        self.assertIsNotNone(plan)
        
        # Verify Goal-Oriented Planning metrics
        self.assertIn("app.py", plan.expected_outputs)
        self.assertIn("templates/index.html", plan.expected_outputs)
        self.assertIn("flask", plan.required_dependencies)
        self.assertIn("Missing Python runtime", plan.risk_analysis)
        
        # Verify 9-phase hierarchy
        phase_descriptions = [step.description for step in plan.steps if step.parent_id == plan.steps[0].id]
        self.assertIn("Project Setup", phase_descriptions)
        self.assertIn("Environment Setup", phase_descriptions)
        self.assertIn("Dependency Installation", phase_descriptions)
        self.assertIn("Source Code Generation", phase_descriptions)
        self.assertIn("Validation", phase_descriptions)
        self.assertIn("Execution", phase_descriptions)
        self.assertIn("Verification", phase_descriptions)

    def test_react_app_template(self):
        goal = Goal(description="Create a React application in project my-app")
        result = self.planner.create_plan(goal)
        
        self.assertTrue(result.success)
        plan = result.plan
        self.assertIn("src/App.js", plan.expected_outputs)
        self.assertIn("node", plan.goal.target_resources or ["node"])

    def test_python_calculator_template(self):
        goal = Goal(description="Build a Python CLI calculator")
        result = self.planner.create_plan(goal)
        
        self.assertTrue(result.success)
        plan = result.plan
        self.assertIn("main.py", plan.expected_outputs)
        self.assertEqual(plan.required_dependencies, [])

    def test_portfolio_website_template(self):
        goal = Goal(description="Build a static portfolio website")
        result = self.planner.create_plan(goal)
        
        self.assertTrue(result.success)
        plan = result.plan
        self.assertIn("index.html", plan.expected_outputs)

    def test_rest_api_template(self):
        goal = Goal(description="Build a FastAPI REST API")
        result = self.planner.create_plan(goal)
        
        self.assertTrue(result.success)
        plan = result.plan
        self.assertIn("app/main.py", plan.expected_outputs)
        self.assertIn("fastapi", plan.required_dependencies)

    def test_cpp_project_template(self):
        goal = Goal(description="Create a C++ project")
        result = self.planner.create_plan(goal)
        
        self.assertTrue(result.success)
        plan = result.plan
        self.assertIn("main.cpp", plan.expected_outputs)

    def test_rust_cli_template(self):
        goal = Goal(description="Build a Rust CLI tool")
        result = self.planner.create_plan(goal)
        
        self.assertTrue(result.success)
        plan = result.plan
        self.assertIn("Cargo.toml", plan.expected_outputs)

    def test_dynamic_adaptation_missing_files(self):
        project_dir = "my_project"
        goal = Goal(description=f"Build a Flask website in project {project_dir}")
        result = self.planner.create_plan(goal)
        self.assertTrue(result.success)
        
        # Test adaptation manually by removing a required file from the steps list
        steps = result.plan.steps
        # Filter out the generate app.py step
        steps_without_app = [s for s in steps if s.expected_artifact != f"{project_dir}/app.py"]
        
        details = self.planner._get_template_details("flask", project_dir)
        root_id = steps[0].id
        
        # Re-run adaptation. It should insert the missing generation step back in!
        adapted_steps = self.planner._adapt_plan_for_missing_prerequisites(steps_without_app, details, project_dir, root_id)
        
        app_file_step = next((s for s in adapted_steps if s.description == f"Generate missing file \'{project_dir}/app.py\'"), None)
        self.assertIsNotNone(app_file_step)
        self.assertEqual(app_file_step.metadata["params"]["operation"], "create")

    def test_artifact_dependency_resolution(self):
        project_dir = "my_api"
        goal = Goal(description=f"Build a FastAPI REST API in project {project_dir}")
        result = self.planner.create_plan(goal)
        
        self.assertTrue(result.success)
        plan = result.plan
        
        # Verify artifact dependencies
        steps = plan.steps
        app_file_step = next((s for s in steps if s.expected_artifact == f"{project_dir}/app/main.py"), None)
        self.assertIsNotNone(app_file_step)

if __name__ == "__main__":
    unittest.main()
