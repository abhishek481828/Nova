"""Unit & Integration tests for Phase F: Accessibility & App Automation System."""

import unittest
from unittest.mock import patch, MagicMock
from nova.actions.app_automation import (
    AppLaunchAction, AppListAction, AccessibilityDumpTreeAction,
    AccessibilityClickAction, AccessibilityTypeAction,
    AccessibilityScrollAction, GlobalGestureAction
)
from nova.automation.engine import UIAutomationEngine, AutomationStep


class TestAccessibilityAutomation(unittest.TestCase):

    @patch("nova.actions.app_automation.send_companion_command")
    def test_app_launch_success(self, mock_cmd):
        mock_cmd.return_value = {
            "status": "success",
            "data": {"app_name": "Calculator", "package_name": "com.sec.android.app.popupcalculator"}
        }
        action = AppLaunchAction()
        result = action.execute({"app_name": "Calculator"})
        self.assertIn("Successfully launched", result)
        self.assertIn("Calculator", result)

    @patch("nova.actions.app_automation.send_companion_command")
    def test_app_list_success(self, mock_cmd):
        mock_cmd.return_value = {
            "status": "success",
            "data": {
                "apps": [
                    {"app_name": "YouTube", "package_name": "com.google.android.youtube"},
                    {"app_name": "Chrome", "package_name": "com.android.chrome"}
                ]
            }
        }
        action = AppListAction()
        result = action.execute({})
        self.assertIn("Found 2 installed applications", result)
        self.assertIn("YouTube", result)
        self.assertIn("Chrome", result)

    @patch("nova.actions.app_automation.send_companion_command")
    def test_accessibility_dump_tree(self, mock_cmd):
        mock_cmd.return_value = {
            "status": "success",
            "data": {
                "package_name": "com.google.android.youtube",
                "root": {"text": "Search", "clickable": True}
            }
        }
        action = AccessibilityDumpTreeAction()
        result = action.execute({})
        self.assertIn("Active Window UI Tree Dumped", result)
        self.assertIn("com.google.android.youtube", result)

    @patch("nova.actions.app_automation.send_companion_command")
    def test_accessibility_click_success(self, mock_cmd):
        mock_cmd.return_value = {"status": "success", "data": {"clicked_target": "Search"}}
        action = AccessibilityClickAction()
        result = action.execute({"target": "Search"})
        self.assertIn("Successfully clicked", result)
        mock_cmd.assert_called_once_with("accessibility.click", {"target": "Search"})

    @patch("nova.actions.app_automation.send_companion_command")
    def test_accessibility_type_success(self, mock_cmd):
        mock_cmd.return_value = {"status": "success", "data": {"typed_text": "Lo-fi Music"}}
        action = AccessibilityTypeAction()
        result = action.execute({"target": "SearchInput", "text": "Lo-fi Music"})
        self.assertIn("Successfully typed text", result)
        mock_cmd.assert_called_once_with("accessibility.type", {
            "target": "SearchInput",
            "text": "Lo-fi Music",
            "replace": True
        })

    @patch("nova.actions.app_automation.send_companion_command")
    def test_accessibility_scroll(self, mock_cmd):
        mock_cmd.return_value = {"status": "success", "data": {"direction": "down"}}
        action = AccessibilityScrollAction()
        result = action.execute({"direction": "down"})
        self.assertIn("Successfully scrolled down", result)

    @patch("nova.actions.app_automation.send_companion_command")
    def test_global_gesture(self, mock_cmd):
        mock_cmd.return_value = {"status": "success", "data": {"global_action": "HOME"}}
        action = GlobalGestureAction()
        result = action.execute({"gesture": "home"})
        self.assertIn("Successfully performed global gesture 'HOME'", result)
        mock_cmd.assert_called_once_with("global.home", {})

    @patch("nova.actions.app_automation.send_companion_command")
    def test_automation_engine_sequence(self, mock_cmd):
        mock_cmd.return_value = {"status": "success", "data": {}}

        engine = UIAutomationEngine()
        steps = [
            AutomationStep(action="app_launch", params={"app_name": "YouTube"}, delay_seconds=0),
            AutomationStep(action="accessibility_click", params={"target": "Search"}, delay_seconds=0),
            AutomationStep(action="accessibility_type", params={"text": "Lo-fi Music"}, delay_seconds=0),
            AutomationStep(action="global_gesture", params={"gesture": "home"}, delay_seconds=0)
        ]

        res = engine.run_sequence(steps)
        self.assertTrue(res.success)
        self.assertEqual(res.steps_completed, 4)
        self.assertEqual(res.total_steps, 4)


if __name__ == "__main__":
    unittest.main()
