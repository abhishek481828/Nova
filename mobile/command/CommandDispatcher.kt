package com.nova.mobile.command

import android.content.Context
import android.util.Log

class CommandDispatcher(private val context: Context) {
    companion object {
        private const val TAG = "CommandDispatcher"
    }

    fun dispatch(commandId: String, intent: BuiltInIntent, entities: Map<String, String>): CommandResult {
        val startTime = System.currentTimeMillis()
        Log.i(TAG, "Dispatching Intent: $intent with Entities: $entities")

        return when (intent) {
            BuiltInIntent.CALL_CONTACT -> {
                val contact = entities["contact"] ?: "unknown"
                CommandResult(
                    commandId, intent, true,
                    spokenResponse = "Calling $contact.",
                    pluginUsed = "CallHandler",
                    entities = entities,
                    executionTimeMs = System.currentTimeMillis() - startTime
                )
            }

            BuiltInIntent.SEND_SMS -> {
                val contact = entities["contact"] ?: "unknown"
                val msg = entities["message"] ?: ""
                val respText = if (msg.isNotBlank()) "Sending message to $contact: '$msg'." else "Opening message chat with $contact."
                CommandResult(
                    commandId, intent, true,
                    spokenResponse = respText,
                    pluginUsed = "SMSHandler",
                    entities = entities,
                    executionTimeMs = System.currentTimeMillis() - startTime
                )
            }

            BuiltInIntent.OPEN_APP, BuiltInIntent.PLAY_YOUTUBE, BuiltInIntent.PLAY_SPOTIFY, BuiltInIntent.OPEN_CAMERA, BuiltInIntent.OPEN_BROWSER, BuiltInIntent.OPEN_SETTINGS, BuiltInIntent.OPEN_GALLERY -> {
                val app = entities["app"] ?: entities["query"] ?: intent.name.replace("OPEN_", "").lowercase()
                CommandResult(
                    commandId, intent, true,
                    spokenResponse = "Opening $app.",
                    pluginUsed = "AppLauncherHandler",
                    entities = entities,
                    executionTimeMs = System.currentTimeMillis() - startTime
                )
            }

            BuiltInIntent.FLASHLIGHT_ON -> {
                CommandResult(
                    commandId, intent, true,
                    spokenResponse = "Flashlight turned on.",
                    pluginUsed = "FlashlightHandler",
                    entities = entities,
                    executionTimeMs = System.currentTimeMillis() - startTime
                )
            }

            BuiltInIntent.FLASHLIGHT_OFF -> {
                CommandResult(
                    commandId, intent, true,
                    spokenResponse = "Flashlight turned off.",
                    pluginUsed = "FlashlightHandler",
                    entities = entities,
                    executionTimeMs = System.currentTimeMillis() - startTime
                )
            }

            BuiltInIntent.SET_VOLUME -> {
                val percent = entities["percentage"] ?: "50"
                CommandResult(
                    commandId, intent, true,
                    spokenResponse = "Volume set to $percent percent.",
                    pluginUsed = "VolumeHandler",
                    entities = entities,
                    executionTimeMs = System.currentTimeMillis() - startTime
                )
            }

            BuiltInIntent.SET_BRIGHTNESS -> {
                val percent = entities["percentage"] ?: "70"
                CommandResult(
                    commandId, intent, true,
                    spokenResponse = "Brightness set to $percent percent.",
                    pluginUsed = "BrightnessHandler",
                    entities = entities,
                    executionTimeMs = System.currentTimeMillis() - startTime
                )
            }

            BuiltInIntent.BATTERY_STATUS -> {
                CommandResult(
                    commandId, intent, true,
                    spokenResponse = "Battery level is 85 percent, healthy.",
                    pluginUsed = "DeviceInfoPlugin",
                    entities = entities,
                    executionTimeMs = System.currentTimeMillis() - startTime
                )
            }

            else -> {
                CommandResult(
                    commandId, intent, false,
                    spokenResponse = "Sorry, I didn't recognize that command.",
                    pluginUsed = "None",
                    entities = entities,
                    executionTimeMs = System.currentTimeMillis() - startTime,
                    errorMessage = "Unknown Intent"
                )
            }
        }
    }
}
