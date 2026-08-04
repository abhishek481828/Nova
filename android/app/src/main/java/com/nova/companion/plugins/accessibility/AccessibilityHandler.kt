package com.nova.companion.plugins.accessibility

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.util.Log
import com.nova.companion.accessibility.NovaAccessibilityService
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONObject

class AccessibilityHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "accessibility"
    override val supportedActions: List<String> = listOf(
        "accessibility.dump_tree",
        "accessibility.click",
        "accessibility.type",
        "accessibility.scroll",
        "accessibility.status",
        "global.home",
        "global.back",
        "global.recents",
        "global.notifications",
        "global.quick_settings"
    )

    override fun execute(action: String, payload: JSONObject): ActionResult {
        val service = NovaAccessibilityService.getInstance()
        val isEnabled = NovaAccessibilityService.isAccessibilityEnabled(context)

        if (action == "accessibility.status") {
            val data = JSONObject().apply {
                put("enabled", isEnabled)
                put("service_running", service != null)
            }
            return ActionResult("success", data = data)
        }

        if (!isEnabled || service == null) {
            return ActionResult(
                "error",
                error = "Nova Accessibility Service is disabled on phone. Please enable it in Phone Settings > Accessibility > Installed Apps > Nova Companion.",
                errorCode = "ACCESSIBILITY_DISABLED"
            )
        }

        return when (action) {
            "accessibility.dump_tree" -> {
                val treeJson = service.dumpUiTree()
                ActionResult("success", data = treeJson)
            }

            "accessibility.click" -> {
                val target = payload.optString("target", payload.optString("text", ""))
                if (target.isEmpty()) {
                    return ActionResult("error", error = "Missing target element text/ID for click action")
                }
                val clicked = service.clickElement(target)
                if (clicked) {
                    ActionResult("success", data = JSONObject().apply { put("clicked_target", target) })
                } else {
                    ActionResult("error", error = "Could not find or click UI element matching '$target'", errorCode = "ELEMENT_NOT_FOUND")
                }
            }

            "accessibility.type" -> {
                val text = payload.optString("text", "")
                val target = payload.optString("target", "")
                val replace = payload.optBoolean("replace", true)

                val typed = service.typeText(if (target.isEmpty()) null else target, text, replace)
                if (typed) {
                    ActionResult("success", data = JSONObject().apply { put("typed_text", text) })
                } else {
                    ActionResult("error", error = "Could not locate editable field to type '$text'", errorCode = "EDITABLE_FIELD_NOT_FOUND")
                }
            }

            "accessibility.scroll" -> {
                val direction = payload.optString("direction", "down")
                val scrolled = service.scroll(direction)
                if (scrolled) {
                    ActionResult("success", data = JSONObject().apply { put("direction", direction) })
                } else {
                    ActionResult("error", error = "Active window is not scrollable in direction '$direction'", errorCode = "NOT_SCROLLABLE")
                }
            }

            "global.home" -> performGlobalAction(service, AccessibilityService.GLOBAL_ACTION_HOME, "HOME")
            "global.back" -> performGlobalAction(service, AccessibilityService.GLOBAL_ACTION_BACK, "BACK")
            "global.recents" -> performGlobalAction(service, AccessibilityService.GLOBAL_ACTION_RECENTS, "RECENTS")
            "global.notifications" -> performGlobalAction(service, AccessibilityService.GLOBAL_ACTION_NOTIFICATIONS, "NOTIFICATIONS")
            "global.quick_settings" -> performGlobalAction(service, AccessibilityService.GLOBAL_ACTION_QUICK_SETTINGS, "QUICK_SETTINGS")

            else -> ActionResult("error", error = "Unsupported accessibility action: $action")
        }
    }

    private fun performGlobalAction(service: NovaAccessibilityService, globalActionCode: Int, actionName: String): ActionResult {
        val success = service.performGlobalAction(globalActionCode)
        return if (success) {
            ActionResult("success", data = JSONObject().apply { put("global_action", actionName) })
        } else {
            ActionResult("error", error = "Failed to perform global action $actionName", errorCode = "GLOBAL_ACTION_FAILED")
        }
    }
}
