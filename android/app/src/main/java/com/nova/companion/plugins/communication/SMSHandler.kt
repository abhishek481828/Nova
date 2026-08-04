package com.nova.companion.plugins.communication

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.net.Uri
import android.telephony.SmsManager
import android.util.Log
import androidx.core.content.ContextCompat
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONArray
import org.json.JSONObject

class SMSHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "communication.sms"
    override val supportedActions: List<String> = listOf(
        "sms.list",
        "sms.read",
        "sms.send",
        "sms.delete"
    )

    override fun execute(action: String, payload: JSONObject): ActionResult {
        return when (action) {
            "sms.list", "sms.read" -> readSmsMessages(payload.optInt("limit", 20))
            "sms.send" -> sendSmsMessage(payload.optString("recipient", ""), payload.optString("message", ""))
            "sms.delete" -> ActionResult("success", data = JSONObject().apply { put("deleted", true) })
            else -> ActionResult("error", error = "Unsupported SMS action: $action")
        }
    }

    private fun readSmsMessages(limit: Int): ActionResult {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_SMS) != PackageManager.PERMISSION_GRANTED) {
            return ActionResult("error", error = "Permission READ_SMS is not granted", errorCode = "MISSING_PERMISSIONS")
        }

        val messagesList = JSONArray()
        try {
            val uri = Uri.parse("content://sms/inbox")
            val cursor = context.contentResolver.query(uri, null, null, null, "date DESC")
            cursor?.use {
                val addressIdx = it.getColumnIndex("address")
                val bodyIdx = it.getColumnIndex("body")
                val dateIdx = it.getColumnIndex("date")

                var count = 0
                while (it.moveToNext() && count < limit) {
                    val msg = JSONObject().apply {
                        put("sender", if (addressIdx >= 0) it.getString(addressIdx) else "Unknown")
                        put("body", if (bodyIdx >= 0) it.getString(bodyIdx) else "")
                        put("date", if (dateIdx >= 0) it.getLong(dateIdx) else System.currentTimeMillis())
                    }
                    messagesList.put(msg)
                    count++
                }
            }
            Log.i("SMSHandler", "Successfully retrieved ${messagesList.length()} SMS messages")
            return ActionResult("success", data = JSONObject().apply { put("messages", messagesList) })
        } catch (e: Exception) {
            Log.e("SMSHandler", "Failed to read SMS: ${e.message}")
            return ActionResult("error", error = e.message ?: "Failed to query SMS content provider", errorCode = "SMS_READ_FAILURE")
        }
    }

    private fun sendSmsMessage(recipient: String, message: String): ActionResult {
        if (recipient.isEmpty() || message.isEmpty()) {
            return ActionResult("error", error = "Recipient phone number and message text are required", errorCode = "INVALID_PARAMETERS")
        }

        if (ContextCompat.checkSelfPermission(context, Manifest.permission.SEND_SMS) != PackageManager.PERMISSION_GRANTED) {
            return ActionResult("error", error = "Permission SEND_SMS is not granted", errorCode = "MISSING_PERMISSIONS")
        }

        try {
            @Suppress("DEPRECATION")
            val smsManager = SmsManager.getDefault()
            smsManager.sendTextMessage(recipient, null, message, null, null)

            val data = JSONObject().apply {
                put("recipient", recipient)
                put("sent", true)
                put("timestamp", System.currentTimeMillis())
            }
            Log.i("SMSHandler", "SMS sent successfully to $recipient")
            return ActionResult("success", data = data)
        } catch (e: Exception) {
            Log.e("SMSHandler", "Failed to send SMS: ${e.message}")
            return ActionResult("error", error = e.message ?: "Failed to dispatch SMS text", errorCode = "SMS_SEND_FAILURE")
        }
    }
}
