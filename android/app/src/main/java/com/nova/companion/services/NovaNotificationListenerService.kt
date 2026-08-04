package com.nova.companion.services

import android.app.Notification
import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import android.util.Log
import org.json.JSONObject
import java.util.regex.Pattern

class NovaNotificationListenerService : NotificationListenerService() {

    companion object {
        var instance: NovaNotificationListenerService? = null
            private set

        private val OTP_PATTERN = Pattern.compile("(?i)(?:code|otp|pin|verify|verification|auth)[^\\d]*(\\d{4,8})")
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        instance = this
        Log.i("NotificationService", "Nova Notification Listener Service connected.")
    }

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        if (sbn == null) return

        try {
            val packageName = sbn.packageName
            val extras = sbn.notification.extras
            val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: ""
            val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""
            val subText = extras.getCharSequence(Notification.EXTRA_SUB_TEXT)?.toString() ?: ""
            val postTime = sbn.postTime

            if (title.isEmpty() && text.isEmpty()) return

            val payload = JSONObject().apply {
                put("package_name", packageName)
                put("title", title)
                put("text", text)
                put("sub_text", subText)
                put("post_time", postTime)
            }

            // 1. Detect WhatsApp Message
            if (packageName == "com.whatsapp" || packageName == "com.whatsapp.w4b") {
                publishNotificationEvent("whatsapp.received", payload)
            }

            // 2. Detect Missed Call
            val fullText = "$title $text".lowercase()
            if (fullText.contains("missed call") || packageName.contains("telecom") || packageName.contains("dialer")) {
                if (fullText.contains("missed")) {
                    publishNotificationEvent("call.missed", payload)
                }
            }

            // 3. Detect OTP Verification Code
            val matcher = OTP_PATTERN.matcher(text)
            if (matcher.find()) {
                val otpCode = matcher.group(1)
                val otpPayload = JSONObject().apply {
                    put("otp_code", otpCode)
                    put("source_app", packageName)
                    put("raw_message", text)
                }
                publishNotificationEvent("otp.detected", otpPayload)
            }

            // 4. Publish Standard Notification Received Event
            publishNotificationEvent("notification.received", payload)

        } catch (e: Exception) {
            Log.e("NotificationService", "Error parsing notification: ${e.message}")
        }
    }

    private fun publishNotificationEvent(eventType: str, payload: JSONObject) {
        Log.i("NotificationService", "Notification Event: $eventType -> ${payload.optString("title")}")
        // Routed via WebSocketClientManager instance if active
    }

    override fun onListenerDisconnected() {
        instance = null
        super.onListenerDisconnected()
    }
}

private typealias str = String
