package com.nova.companion.plugins.hardware

import android.content.Context
import android.os.Build
import android.os.VibrationEffect
import android.os.Vibrator
import android.os.VibratorManager
import android.util.Log
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONObject

class VibrationHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "hardware.vibration"
    override val supportedActions: List<String> = listOf(
        "vibration.short",
        "vibration.medium",
        "vibration.long",
        "vibration.custom"
    )

    override fun execute(action: String, payload: JSONObject): ActionResult {
        val vibrator = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val vm = context.getSystemService(Context.VIBRATOR_MANAGER_SERVICE) as? VibratorManager
            vm?.defaultVibrator
        } else {
            @Suppress("DEPRECATION")
            context.getSystemService(Context.VIBRATOR_SERVICE) as? Vibrator
        } ?: return ActionResult("error", error = "Vibrator service not available", errorCode = "HARDWARE_FAILURE")

        if (!vibrator.hasVibrator()) {
            return ActionResult("error", error = "Device does not support vibration", errorCode = "HARDWARE_NOT_AVAILABLE")
        }

        try {
            val durationMs: Long = when (action) {
                "vibration.short" -> 150L
                "vibration.medium" -> 500L
                "vibration.long" -> 1000L
                "vibration.custom" -> payload.optLong("duration_ms", 300L)
                else -> 300L
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                vibrator.vibrate(VibrationEffect.createOneShot(durationMs, VibrationEffect.DEFAULT_AMPLITUDE))
            } else {
                @Suppress("DEPRECATION")
                vibrator.vibrate(durationMs)
            }

            val data = JSONObject().apply {
                put("duration_ms", durationMs)
                put("pattern", action)
            }
            Log.i("VibrationHandler", "Vibration action $action executed ($durationMs ms)")
            return ActionResult("success", data = data)

        } catch (e: Exception) {
            Log.e("VibrationHandler", "Vibration execution error: ${e.message}")
            return ActionResult("error", error = e.message ?: "Failed to trigger vibration", errorCode = "HARDWARE_FAILURE")
        }
    }
}
