package com.nova.companion.plugins.hardware

import android.content.Context
import android.hardware.camera2.CameraCharacteristics
import android.hardware.camera2.CameraManager
import android.util.Log
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONObject

class FlashlightHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "hardware.flashlight"
    override val supportedActions: List<String> = listOf(
        "flashlight.on",
        "flashlight.off",
        "flashlight.toggle",
        "flashlight.status"
    )

    private var isTorchOn = false

    override fun execute(action: String, payload: JSONObject): ActionResult {
        val cameraManager = context.getSystemService(Context.CAMERA_SERVICE) as? CameraManager
            ?: return ActionResult("error", error = "CameraManager service not available", errorCode = "FLASHLIGHT_NOT_AVAILABLE")

        val cameraId = getCameraIdWithFlash(cameraManager)
            ?: return ActionResult("error", error = "Device does not support flashlight / torch", errorCode = "FLASHLIGHT_NOT_AVAILABLE")

        try {
            when (action) {
                "flashlight.on" -> {
                    cameraManager.setTorchMode(cameraId, true)
                    isTorchOn = true
                }
                "flashlight.off" -> {
                    cameraManager.setTorchMode(cameraId, false)
                    isTorchOn = false
                }
                "flashlight.toggle" -> {
                    isTorchOn = !isTorchOn
                    cameraManager.setTorchMode(cameraId, isTorchOn)
                }
                "flashlight.status" -> {
                    // Just query state
                }
                else -> return ActionResult("error", error = "Unsupported flashlight action: $action")
            }

            val data = JSONObject().apply {
                put("state", if (isTorchOn) "on" else "off")
                put("is_available", true)
            }
            Log.i("FlashlightHandler", "Flashlight action $action executed. New state: ${if (isTorchOn) "on" else "off"}")
            return ActionResult("success", data = data)

        } catch (e: Exception) {
            Log.e("FlashlightHandler", "Flashlight execution error: ${e.message}")
            return ActionResult("error", error = e.message ?: "Failed to set torch mode", errorCode = "HARDWARE_FAILURE")
        }
    }

    private fun getCameraIdWithFlash(cameraManager: CameraManager): String? {
        try {
            for (id in cameraManager.cameraIdList) {
                val characteristics = cameraManager.getCameraCharacteristics(id)
                val hasFlash = characteristics.get(CameraCharacteristics.FLASH_INFO_AVAILABLE) ?: false
                val facing = characteristics.get(CameraCharacteristics.LENS_FACING)
                if (hasFlash && facing == CameraCharacteristics.LENS_FACING_BACK) {
                    return id
                }
            }
        } catch (e: Exception) {
            Log.e("FlashlightHandler", "Error detecting camera flash: ${e.message}")
        }
        return null
    }
}
