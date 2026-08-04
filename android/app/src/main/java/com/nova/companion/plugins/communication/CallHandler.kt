package com.nova.companion.plugins.communication

import android.Manifest
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.provider.CallLog
import android.util.Log
import androidx.core.content.ContextCompat
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONArray
import org.json.JSONObject

class CallHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "communication.calls"
    override val supportedActions: List<String> = listOf(
        "call.make",
        "call.end",
        "call.history",
        "call.status",
        "call.missed"
    )

    override fun execute(action: String, payload: JSONObject): ActionResult {
        return when (action) {
            "call.make" -> makeCall(payload.optString("number", ""))
            "call.end" -> ActionResult("success", data = JSONObject().apply { put("ended", true) })
            "call.history", "call.missed" -> getCallLog(payload.optInt("limit", 20), isMissedOnly = (action == "call.missed"))
            "call.status" -> ActionResult("success", data = JSONObject().apply { put("status", "idle") })
            else -> ActionResult("error", error = "Unsupported call action: $action")
        }
    }

    private fun makeCall(phoneNumber: String): ActionResult {
        if (phoneNumber.isEmpty()) {
            return ActionResult("error", error = "Phone number is required", errorCode = "INVALID_PARAMETERS")
        }

        if (ContextCompat.checkSelfPermission(context, Manifest.permission.CALL_PHONE) != PackageManager.PERMISSION_GRANTED) {
            return ActionResult("error", error = "Permission CALL_PHONE is not granted", errorCode = "MISSING_PERMISSIONS")
        }

        try {
            val intent = Intent(Intent.ACTION_CALL).apply {
                data = Uri.parse("tel:$phoneNumber")
                flags = Intent.FLAG_ACTIVITY_NEW_TASK
            }
            context.startActivity(intent)

            val data = JSONObject().apply {
                put("number", phoneNumber)
                put("initiated", true)
            }
            Log.i("CallHandler", "Phone call initiated to $phoneNumber")
            return ActionResult("success", data = data)
        } catch (e: Exception) {
            Log.e("CallHandler", "Failed to initiate call: ${e.message}")
            return ActionResult("error", error = e.message ?: "Failed to trigger phone call", errorCode = "CALL_FAILURE")
        }
    }

    private fun getCallLog(limit: Int, isMissedOnly: Boolean): ActionResult {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CALL_LOG) != PackageManager.PERMISSION_GRANTED) {
            return ActionResult("error", error = "Permission READ_CALL_LOG is not granted", errorCode = "MISSING_PERMISSIONS")
        }

        val logsList = JSONArray()
        try {
            val selection = if (isMissedOnly) "${CallLog.Calls.TYPE} = ${CallLog.Calls.MISSED_TYPE}" else null
            val cursor = context.contentResolver.query(
                CallLog.Calls.CONTENT_URI,
                null,
                selection,
                null,
                "${CallLog.Calls.DATE} DESC"
            )
            cursor?.use {
                val numIdx = it.getColumnIndex(CallLog.Calls.NUMBER)
                val typeIdx = it.getColumnIndex(CallLog.Calls.TYPE)
                val dateIdx = it.getColumnIndex(CallLog.Calls.DATE)
                val durIdx = it.getColumnIndex(CallLog.Calls.DURATION)

                var count = 0
                while (it.moveToNext() && count < limit) {
                    val log = JSONObject().apply {
                        put("number", if (numIdx >= 0) it.getString(numIdx) else "Unknown")
                        put("type", if (typeIdx >= 0) it.getInt(typeIdx) else 0)
                        put("date", if (dateIdx >= 0) it.getLong(dateIdx) else System.currentTimeMillis())
                        put("duration_seconds", if (durIdx >= 0) it.getInt(durIdx) else 0)
                    }
                    logsList.put(log)
                    count++
                }
            }
            Log.i("CallHandler", "Retrieved ${logsList.length()} call log entries")
            return ActionResult("success", data = JSONObject().apply { put("calls", logsList) })
        } catch (e: Exception) {
            Log.e("CallHandler", "Failed to query call log: ${e.message}")
            return ActionResult("error", error = e.message ?: "Failed to query CallLog", errorCode = "CALL_LOG_FAILURE")
        }
    }
}
