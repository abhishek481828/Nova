package com.nova.companion.plugins.system

import android.content.ClipData
import android.content.ClipboardManager
import android.content.Context
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONObject

class ClipboardHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "system.clipboard"
    override val supportedActions: List<String> = listOf("clipboard.get", "clipboard.set")

    override fun execute(action: String, payload: JSONObject): ActionResult {
        val clipboard = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager

        return when (action) {
            "clipboard.get" -> {
                val clipText = clipboard.primaryClip?.getItemAt(0)?.text?.toString() ?: ""
                val data = JSONObject().apply {
                    put("text", clipText)
                }
                ActionResult("success", data = data)
            }
            "clipboard.set" -> {
                val text = payload.optString("text", "")
                val clip = ClipData.newPlainText("Nova Clipboard", text)
                clipboard.setPrimaryClip(clip)
                val data = JSONObject().apply {
                    put("status", "copied")
                    put("text", text)
                }
                ActionResult("success", data = data)
            }
            else -> ActionResult("error", error = "Unsupported clipboard action")
        }
    }
}
