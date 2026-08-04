package com.nova.mobile.command

import android.content.Context
import android.util.Log
import com.nova.mobile.lifecycle.LifecycleManager

typealias CommandExecutionListener = (result: CommandResult) -> Unit

class CommandEngine(
    private val context: Context,
    private val lifecycleManager: LifecycleManager
) {
    companion object {
        private const val TAG = "CommandEngine"
    }

    val intentParser: IntentParser by lazy { IntentParser() }
    val entityExtractor: EntityExtractor by lazy { EntityExtractor() }
    val executionContext: ExecutionContext by lazy { ExecutionContext() }
    val dispatcher: CommandDispatcher by lazy { CommandDispatcher(context) }
    val history: CommandHistory = CommandHistory()

    private val executionListeners = mutableListOf<CommandExecutionListener>()

    fun executeText(text: String): CommandResult {
        val commandId = java.util.UUID.randomUUID().toString()
        Log.i(TAG, "CommandEngine executing speech text: \"$text\" (Command ID: $commandId)")

        lifecycleManager.publishEvent("CommandStarted", mapOf("commandId" to commandId, "text" to text))

        val intent = intentParser.parse(text)
        if (intent == BuiltInIntent.UNKNOWN) {
            lifecycleManager.publishEvent("UnknownIntent", mapOf("commandId" to commandId, "text" to text))
            val errorResult = CommandResult(
                commandId, intent, false,
                spokenResponse = "I'm sorry, I didn't understand that command.",
                pluginUsed = "None",
                errorMessage = "Unknown Intent"
            )
            history.record(errorResult)
            notifyListeners(errorResult)
            return errorResult
        }

        lifecycleManager.publishEvent("IntentRecognized", mapOf("commandId" to commandId, "intent" to intent.name))

        val entities = entityExtractor.extract(text, intent, executionContext)
        val result = dispatcher.dispatch(commandId, intent, entities)

        history.record(result)

        if (result.isSuccess) {
            lifecycleManager.publishEvent(
                "CommandCompleted",
                mapOf(
                    "commandId" to commandId,
                    "intent" to intent.name,
                    "response" to result.spokenResponse,
                    "plugin" to result.pluginUsed
                )
            )
        } else {
            lifecycleManager.publishEvent(
                "CommandFailed",
                mapOf("commandId" to commandId, "reason" to (result.errorMessage ?: "Execution Error"))
            )
        }

        notifyListeners(result)
        return result
    }

    fun addExecutionListener(listener: CommandExecutionListener) {
        executionListeners.add(listener)
    }

    fun removeExecutionListener(listener: CommandExecutionListener) {
        executionListeners.remove(listener)
    }

    private fun notifyListeners(result: CommandResult) {
        for (l in executionListeners) {
            try {
                l(result)
            } catch (e: Exception) {
                Log.e(TAG, "Error in command execution listener", e)
            }
        }
    }
}
