"""Phase F: Reusable UI Automation Engine for Nova v2.0."""

import time
import logging
from typing import List, Dict, Any, Optional

logger = logging.getLogger("nova.automation.engine")


class AutomationStep:
    def __init__(
        self,
        action: str,
        params: Optional[Dict[str, Any]] = None,
        delay_seconds: float = 1.0,
        retries: int = 3,
        timeout_seconds: float = 10.0
    ):
        self.action = action
        self.params = params or {}
        self.delay_seconds = delay_seconds
        self.retries = retries
        self.timeout_seconds = timeout_seconds


class AutomationResult:
    def __init__(self, success: Boolean if False else bool, steps_completed: int, total_steps: int, logs: List[str], error: Optional[str] = None):
        self.success = success
        self.steps_completed = steps_completed
        self.total_steps = total_steps
        self.logs = logs
        self.error = error

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "steps_completed": self.steps_completed,
            "total_steps": self.total_steps,
            "logs": self.logs,
            "error": self.error
        }


class UIAutomationEngine:
    def __init__(self, action_registry=None):
        self.action_registry = action_registry

    def _execute_single_action(self, action_name: str, params: Dict[str, Any]) -> str:
        from nova.actions.phone_control import send_companion_command, PhoneCameraAction
        from nova.actions.app_automation import (
            AppLaunchAction, AppListAction, AccessibilityClickAction,
            AccessibilityTypeAction, AccessibilityScrollAction, GlobalGestureAction
        )

        action_map = {
            "app_launch": AppLaunchAction(),
            "app.launch": AppLaunchAction(),
            "app_list": AppListAction(),
            "app.list": AppListAction(),
            "accessibility_click": AccessibilityClickAction(),
            "accessibility.click": AccessibilityClickAction(),
            "click": AccessibilityClickAction(),
            "accessibility_type": AccessibilityTypeAction(),
            "accessibility.type": AccessibilityTypeAction(),
            "type": AccessibilityTypeAction(),
            "accessibility_scroll": AccessibilityScrollAction(),
            "accessibility.scroll": AccessibilityScrollAction(),
            "scroll": AccessibilityScrollAction(),
            "global_gesture": GlobalGestureAction(),
            "global.home": GlobalGestureAction(),
            "global.back": GlobalGestureAction(),
        }

        act = action_map.get(action_name)
        if act:
            return act.execute(params)
        else:
            res = send_companion_command(action_name, params)
            if res.get("status") == "success":
                return f"Executed {action_name} successfully."
            raise RuntimeError(res.get("error", f"Action {action_name} failed"))

    def run_sequence(self, steps: List[AutomationStep]) -> AutomationResult:
        logs = []
        start_time = time.time()

        for idx, step in enumerate(steps, 1):
            logs.append(f"[Step {idx}/{len(steps)}] Executing '{step.action}' with params={step.params}")
            logger.info(f"Automation Step {idx}/{len(steps)}: {step.action}")

            success = False
            last_error = None

            for attempt in range(1, step.retries + 1):
                try:
                    if step.delay_seconds > 0:
                        time.sleep(step.delay_seconds)

                    res_msg = self._execute_single_action(step.action, step.params)
                    if "Failed" in res_msg or "error" in res_msg.lower():
                        raise RuntimeError(res_msg)

                    logs.append(f"  ✔ Attempt {attempt}: {res_msg}")
                    success = True
                    break
                except Exception as e:
                    last_error = str(e)
                    logs.append(f"  ✘ Attempt {attempt}/{step.retries} failed: {last_error}")
                    if attempt < step.retries:
                        time.sleep(1.0)

            if not success:
                err_msg = f"Step {idx} ('{step.action}') failed after {step.retries} attempts: {last_error}"
                logs.append(f"Automation sequence aborted: {err_msg}")
                return AutomationResult(
                    success=False,
                    steps_completed=idx - 1,
                    total_steps=len(steps),
                    logs=logs,
                    error=err_msg
                )

        logs.append(f"Automation sequence completed successfully in {round(time.time() - start_time, 2)}s.")
        return AutomationResult(
            success=True,
            steps_completed=len(steps),
            total_steps=len(steps),
            logs=logs
        )
