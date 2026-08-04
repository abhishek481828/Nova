package com.nova.companion.plugins.hardware

import android.content.Context
import android.media.AudioManager
import android.util.Log
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONObject

class VolumeHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "hardware.volume"
    override val supportedActions: List<String> = listOf(
        "volume.get",
        "volume.set",
        "volume.increase",
        "volume.decrease",
        "volume.mute"
    )

    override fun execute(action: String, payload: JSONObject): ActionResult {
        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as? AudioManager
            ?: return ActionResult("error", error = "AudioManager not available", errorCode = "HARDWARE_FAILURE")

        val streamTypeStr = payload.optString("stream", "media").lowercase()
        val streamType = getStreamType(streamTypeStr)

        val maxVolume = audioManager.getStreamMaxVolume(streamType)

        try {
            when (action) {
                "volume.get" -> {
                    // Just return current level
                }
                "volume.set" -> {
                    val percent = payload.optInt("percent", -1)
                    val level = if (percent in 0..100) {
                        (percent * maxVolume / 100.0).toInt()
                    } else {
                        payload.optInt("level", audioManager.getStreamVolume(streamType))
                    }
                    audioManager.setStreamVolume(streamType, level.coerceIn(0, maxVolume), 0)
                }
                "volume.increase" -> {
                    val step = payload.optInt("step", 1)
                    val current = audioManager.getStreamVolume(streamType)
                    audioManager.setStreamVolume(streamType, (current + step).coerceIn(0, maxVolume), 0)
                }
                "volume.decrease" -> {
                    val step = payload.optInt("step", 1)
                    val current = audioManager.getStreamVolume(streamType)
                    audioManager.setStreamVolume(streamType, (current - step).coerceIn(0, maxVolume), 0)
                }
                "volume.mute" -> {
                    audioManager.setStreamVolume(streamType, 0, 0)
                }
                else -> return ActionResult("error", error = "Unsupported volume action: $action")
            }

            val currentLevel = audioManager.getStreamVolume(streamType)
            val currentPercent = if (maxVolume > 0) ((currentLevel.toDouble() / maxVolume.toDouble()) * 100.0).toInt() else 0

            val data = JSONObject().apply {
                put("stream", streamTypeStr)
                put("level", currentLevel)
                put("max_level", maxVolume)
                put("percent", currentPercent)
            }
            Log.i("VolumeHandler", "Volume action $action executed for $streamTypeStr. Level=$currentLevel/$maxVolume ($currentPercent%)")
            return ActionResult("success", data = data)

        } catch (e: Exception) {
            Log.e("VolumeHandler", "Volume execution error: ${e.message}")
            return ActionResult("error", error = e.message ?: "Failed to adjust volume", errorCode = "HARDWARE_FAILURE")
        }
    }

    private fun getStreamType(streamName: String): Int {
        return when (streamName) {
            "ring" -> AudioManager.STREAM_RING
            "alarm" -> AudioManager.STREAM_ALARM
            "notification" -> AudioManager.STREAM_NOTIFICATION
            else -> AudioManager.STREAM_MUSIC
        }
    }
}
