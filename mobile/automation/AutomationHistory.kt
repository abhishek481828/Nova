package com.nova.mobile.automation

import android.util.Log

/**
 * AutomationHistory — Immutable, append-only execution log.
 * Stores the last N AutomationResults for dashboard display and debugging.
 */
class AutomationHistory(private val maxSize: Int = 100) {
    companion object { private const val TAG = "AutomationHistory" }

    private val history: ArrayDeque<AutomationResult> = ArrayDeque()

    fun record(result: AutomationResult) {
        if (history.size >= maxSize) history.removeFirst()
        history.addLast(result)
        val status = if (result.isSuccess) "SUCCESS" else "FAILED"
        Log.i(TAG, "[$status] Routine '${result.routineName}' in ${result.executionTimeMs}ms")
    }

    fun getAll(): List<AutomationResult> = history.toList().reversed()

    fun getSuccessful(): List<AutomationResult> = getAll().filter { it.isSuccess }

    fun getFailed(): List<AutomationResult> = getAll().filter { !it.isSuccess }

    fun getRecent(limit: Int = 10): List<AutomationResult> = getAll().take(limit)

    fun getLastResult(): AutomationResult? = history.lastOrNull()

    fun getForRoutine(routineId: String): List<AutomationResult> =
        getAll().filter { it.routineId == routineId }

    fun clear() { history.clear() }

    fun totalCount(): Int = history.size
    fun successCount(): Int = history.count { it.isSuccess }
    fun failureCount(): Int = history.count { !it.isSuccess }
}
