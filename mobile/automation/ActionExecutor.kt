package com.nova.mobile.automation

import android.util.Log
import com.nova.mobile.command.CommandEngine
import kotlinx.coroutines.delay

/**
 * ActionExecutor — Executes a list of AutomationActions sequentially.
 * Reuses the existing CommandEngine to translate actions into plugin calls.
 * Supports per-action delays and error isolation (one failure doesn't abort all).
 */
class ActionExecutor(private val commandEngine: CommandEngine) {
    companion object {
        private const val TAG = "ActionExecutor"
        private const val ACTION_TIMEOUT_MS = 8000L
    }

    data class ActionLog(
        val actionType: String,
        val isSuccess: Boolean,
        val spokenResponse: String,
        val errorMessage: String? = null,
        val durationMs: Long = 0L
    )

    suspend fun execute(actions: List<AutomationAction>): List<ActionLog> {
        val log = mutableListOf<ActionLog>()
        for (action in actions) {
            val start = System.currentTimeMillis()
            val text = buildCommandText(action)
            Log.i(TAG, "Executing action: ${action.type} → \"$text\"")

            val actionLog = try {
                val result = commandEngine.executeText(text)
                ActionLog(
                    actionType = action.type.name,
                    isSuccess = result.isSuccess,
                    spokenResponse = result.spokenResponse,
                    errorMessage = result.errorMessage,
                    durationMs = System.currentTimeMillis() - start
                )
            } catch (e: Exception) {
                Log.e(TAG, "Action ${action.type} failed: ${e.message}")
                ActionLog(
                    actionType = action.type.name,
                    isSuccess = false,
                    spokenResponse = "",
                    errorMessage = e.message,
                    durationMs = System.currentTimeMillis() - start
                )
            }
            log.add(actionLog)

            if (action.delaySecondsAfter > 0) {
                Log.i(TAG, "Waiting ${action.delaySecondsAfter}s before next action…")
                delay(action.delaySecondsAfter * 1000L)
            }
        }
        return log
    }

    /** Translates an AutomationAction into a natural-language string the CommandEngine understands. */
    private fun buildCommandText(action: AutomationAction): String = when (action.type) {
        ActionType.CALL_CONTACT     -> "Call ${action.params["contact"] ?: "unknown"}"
        ActionType.SEND_SMS         -> "Send message to ${action.params["contact"] ?: "unknown"} saying ${action.params["message"] ?: ""}"
        ActionType.OPEN_APP         -> "Open ${action.params["app"] ?: "app"}"
        ActionType.PLAY_YOUTUBE     -> "Open YouTube"
        ActionType.PLAY_MUSIC       -> "Play music"
        ActionType.FLASHLIGHT_ON    -> "Turn on flashlight"
        ActionType.FLASHLIGHT_OFF   -> "Turn off flashlight"
        ActionType.SET_BRIGHTNESS   -> "Set brightness to ${action.params["value"] ?: "50"}%"
        ActionType.SET_VOLUME       -> "Set volume to ${action.params["value"] ?: "50"}%"
        ActionType.ENABLE_BLUETOOTH -> "Enable Bluetooth"
        ActionType.DISABLE_BLUETOOTH-> "Disable Bluetooth"
        ActionType.ENABLE_DND       -> "Enable Do Not Disturb"
        ActionType.DISABLE_DND      -> "Disable Do Not Disturb"
        ActionType.SET_ALARM        -> "Set alarm for ${action.params["time"] ?: "7:00 AM"}"
        ActionType.SET_TIMER        -> "Set timer for ${action.params["minutes"] ?: "10"} minutes"
        ActionType.OPEN_CAMERA      -> "Open camera"
        ActionType.OPEN_GALLERY     -> "Open gallery"
        ActionType.COPY_TEXT        -> "Copy ${action.params["text"] ?: ""}"
        ActionType.SHOW_NOTIFICATION-> "Show notification ${action.params["message"] ?: ""}"
        ActionType.NOVA_CORE_REQUEST-> action.params["request"] ?: "Nova Core request"
        ActionType.WAIT_SECONDS     -> "Wait"
    }
}
