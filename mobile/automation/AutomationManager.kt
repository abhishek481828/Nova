package com.nova.mobile.automation

import android.context.Context
import android.util.Log
import com.nova.mobile.command.CommandEngine
import com.nova.mobile.lifecycle.LifecycleManager
import kotlinx.coroutines.*
import java.time.Instant

/**
 * AutomationManager — Phase 7 Main Orchestrator.
 *
 * Wires together:
 *   TriggerManager → ConditionEngine → ActionExecutor → AutomationHistory
 *
 * Safety guarantees:
 *   - allPaused flag: no routine runs when paused
 *   - requiresConfirmation flag per routine
 *   - All actions use existing validated CommandEngine/plugins
 *   - Nova NEVER invents routines — only users create them
 */
class AutomationManager(
    private val context: android.content.Context,
    private val lifecycleManager: LifecycleManager,
    commandEngine: CommandEngine
) {
    companion object { private const val TAG = "AutomationManager" }

    val repository = AutomationRepository()
    val history = AutomationHistory()
    val conditionEngine = ConditionEngine()
    val actionExecutor = ActionExecutor(commandEngine)
    val triggerManager = TriggerManager(repository)
    val routineManager = RoutineManager(repository, triggerManager)
    val scheduler = AutomationScheduler(triggerManager)

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val resultListeners = mutableListOf<(AutomationResult) -> Unit>()

    init {
        triggerManager.addListener { routine -> scope.launch { executeRoutine(routine) } }
    }

    fun start() {
        scheduler.start(scope)
        lifecycleManager.publishEvent("AutomationManagerStarted", emptyMap())
        Log.i(TAG, "AutomationManager started")
    }

    fun stop() {
        scheduler.stop()
        scope.cancel()
        lifecycleManager.publishEvent("AutomationManagerStopped", emptyMap())
        Log.i(TAG, "AutomationManager stopped")
    }

    private suspend fun executeRoutine(routine: Routine) {
        if (routineManager.allPaused) {
            Log.w(TAG, "Automations paused — skipping '${routine.name}'")
            return
        }

        val startTime = System.currentTimeMillis()
        Log.i(TAG, "Executing routine: '${routine.name}' (${routine.actions.size} actions)")

        lifecycleManager.publishEvent("RoutineExecutionStarted",
            mapOf("routineId" to routine.id, "name" to routine.name))

        // 1. Evaluate conditions
        if (!conditionEngine.evaluate(routine.conditions)) {
            Log.i(TAG, "Conditions not met for '${routine.name}' — skipping")
            lifecycleManager.publishEvent("RoutineConditionFailed",
                mapOf("routineId" to routine.id))
            return
        }

        // 2. Execute all actions sequentially
        val actionLogs = try {
            actionExecutor.execute(routine.actions)
        } catch (e: Exception) {
            Log.e(TAG, "Routine '${routine.name}' crashed: ${e.message}", e)
            listOf(ActionExecutor.ActionLog(
                "UNKNOWN", false, "", errorMessage = e.message
            ))
        }

        val elapsed = System.currentTimeMillis() - startTime
        val failedAction = actionLogs.firstOrNull { !it.isSuccess }
        val isSuccess = failedAction == null

        // 3. Record in history
        val result = AutomationResult(
            routineId = routine.id,
            routineName = routine.name,
            isSuccess = isSuccess,
            executedActions = actionLogs.filter { it.isSuccess }.map { it.actionType },
            failedAction = failedAction?.actionType,
            errorMessage = failedAction?.errorMessage,
            executionTimeMs = elapsed
        )
        history.record(result)
        repository.recordExecution(routine.id)

        // 4. Publish lifecycle events
        val eventName = if (isSuccess) "RoutineExecutionSucceeded" else "RoutineExecutionFailed"
        lifecycleManager.publishEvent(eventName,
            mapOf("routineId" to routine.id, "name" to routine.name,
                  "elapsed" to elapsed, "actionsRan" to actionLogs.size))

        resultListeners.forEach { it(result) }
        Log.i(TAG, "Routine '${routine.name}' ${if (isSuccess) "SUCCESS" else "FAILED"} in ${elapsed}ms")
    }

    fun handleVoiceQuery(rawText: String): String? =
        routineManager.handleVoiceQuery(rawText)

    fun addResultListener(listener: (AutomationResult) -> Unit) {
        resultListeners.add(listener)
    }
}
