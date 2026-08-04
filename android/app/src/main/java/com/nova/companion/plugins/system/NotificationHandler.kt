package com.nova.companion.plugins.system

import android.app.Notification
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import com.nova.companion.services.NovaNotificationListenerService
import org.json.JSONArray
import org.json.JSONObject

class NotificationHandler : BaseActionHandler {
    override val category: String = "system.notifications"
    override val supportedActions: List<String> = listOf("notification.list_active")

    override fun execute(action: String, payload: JSONObject): ActionResult {
        val service = NovaNotificationListenerService.instance
            ?: return ActionResult("error", error = "Notification Listener Service is not enabled in Android Settings")

        val activeList = service.activeNotifications
        val array = JSONArray()

        for (sbn in activeList) {
            val extras = sbn.notification.extras
            val title = extras.getCharSequence(Notification.EXTRA_TITLE)?.toString() ?: ""
            val text = extras.getCharSequence(Notification.EXTRA_TEXT)?.toString() ?: ""

            val notifJson = JSONObject().apply {
                put("package_name", sbn.packageName)
                put("title", title)
                put("text", text)
                put("post_time", sbn.postTime)
            }
            array.put(notifJson)
        }

        val data = JSONObject().apply {
            put("active_notifications", array)
        }
        return ActionResult("success", data = data)
    }
}
