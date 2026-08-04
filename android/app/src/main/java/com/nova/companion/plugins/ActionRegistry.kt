package com.nova.companion.plugins

import android.util.Log
import org.json.JSONObject

class ActionRegistry {
    private val handlers = mutableMapOf<String, BaseActionHandler>()
    private val actionMap = mutableMapOf<String, BaseActionHandler>()

    fun register(handler: BaseActionHandler) {
        handlers[handler.category] = handler
        for (action in handler.supportedActions) {
            actionMap[action] = handler
            Log.i("ActionRegistry", "Registered action '$action' -> Category '${handler.category}'")
        }
    }

    fun dispatch(action: String, payload: JSONObject): ActionResult {
        val handler = actionMap[action]
            ?: return ActionResult("error", error = "No handler registered for action: $action")

        return try {
            handler.execute(action, payload)
        } catch (e: Exception) {
            ActionResult("error", error = "Execution failed: ${e.message}")
        }
    }

    fun getSupportedActions(): List<String> {
        return actionMap.keys.toList()
    }
}
