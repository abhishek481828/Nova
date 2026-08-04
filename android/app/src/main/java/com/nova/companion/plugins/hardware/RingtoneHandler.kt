package com.nova.companion.plugins.hardware

import android.content.Context
import android.media.Ringtone
import android.media.RingtoneManager
import android.net.Uri
import android.util.Log
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONObject

class RingtoneHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "hardware.ringtone"
    override val supportedActions: List<String> = listOf(
        "ringtone.play",
        "ringtone.stop",
        "ringtone.default",
        "ringtone.custom"
    )

    companion object {
        private var activeRingtone: Ringtone? = null
    }

    override fun execute(action: String, payload: JSONObject): ActionResult {
        try {
            when (action) {
                "ringtone.play", "ringtone.default", "ringtone.custom" -> {
                    activeRingtone?.stop()
                    val uriStr = payload.optString("uri", "")
                    val uri: Uri = if (uriStr.isNotEmpty()) {
                        Uri.parse(uriStr)
                    } else {
                        RingtoneManager.getDefaultUri(RingtoneManager.TYPE_RINGTONE)
                    }

                    activeRingtone = RingtoneManager.getRingtone(context, uri)
                    activeRingtone?.play()

                    val data = JSONObject().apply {
                        put("playing", true)
                        put("uri", uri.toString())
                    }
                    Log.i("RingtoneHandler", "Playing ringtone: ${uri.toString()}")
                    return ActionResult("success", data = data)
                }
                "ringtone.stop" -> {
                    activeRingtone?.stop()
                    activeRingtone = null
                    val data = JSONObject().apply {
                        put("playing", false)
                    }
                    Log.i("RingtoneHandler", "Stopped active ringtone")
                    return ActionResult("success", data = data)
                }
                else -> return ActionResult("error", error = "Unsupported ringtone action: $action")
            }
        } catch (e: Exception) {
            Log.e("RingtoneHandler", "Ringtone execution error: ${e.message}")
            return ActionResult("error", error = e.message ?: "Failed to trigger ringtone", errorCode = "HARDWARE_FAILURE")
        }
    }
}
