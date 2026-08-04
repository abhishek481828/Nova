package com.nova.companion.plugins.system

import android.content.Context
import android.telephony.SmsManager
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONObject

class SMSHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "system.sms"
    override val supportedActions: List<String> = listOf("sms.send")

    override fun execute(action: String, payload: JSONObject): ActionResult {
        val recipient = payload.optString("recipient")
        val message = payload.optString("message")

        if (recipient.isNull_or_empty() || message.isNull_or_empty()) {
            return ActionResult("error", error = "Recipient and message must be provided")
        }

        return try {
            val smsManager = context.getSystemService(SmsManager::class.java)
            smsManager.sendTextMessage(recipient, null, message, null, null)
            val data = JSONObject().apply {
                put("recipient", recipient)
                put("status", "sent")
            }
            ActionResult("success", data = data)
        } catch (e: Exception) {
            ActionResult("error", error = "Failed to send SMS: ${e.message}")
        }
    }

    private fun String?.isNull_or_empty(): Boolean = this == null || this.trim().isEmpty()
}
