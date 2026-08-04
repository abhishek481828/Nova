package com.nova.companion.plugins

import org.json.JSONObject

data class ActionResult(
    val status: String,
    val data: JSONObject = JSONObject(),
    val error: String? = null,
    val errorCode: String? = null
)

interface BaseActionHandler {
    val category: String
    val supportedActions: List<String>
    fun execute(action: String, payload: JSONObject): ActionResult
}
