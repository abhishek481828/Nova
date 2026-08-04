package com.nova.mobile.automation

import android.util.Log
import kotlinx.coroutines.*
import java.time.LocalTime

/**
 * AutomationScheduler — Drives time-based triggers by ticking every minute.
 * Integrates with TriggerManager to fire TIME and DAY_OF_WEEK routines.
 */
class AutomationScheduler(private val triggerManager: TriggerManager) {
    companion object {
        private const val TAG = "AutomationScheduler"
        private const val TICK_INTERVAL_MS = 60_000L
    }

    var isRunning: Boolean = false
        private set

    private var tickJob: Job? = null

    fun start(scope: CoroutineScope = CoroutineScope(Dispatchers.IO)) {
        if (isRunning) return
        isRunning = true
        tickJob = scope.launch {
            Log.i(TAG, "AutomationScheduler started")
            while (isActive) {
                val now = LocalTime.now()
                triggerManager.onTimeTick(now.hour, now.minute)
                delay(TICK_INTERVAL_MS)
            }
        }
    }

    fun stop() {
        tickJob?.cancel()
        tickJob = null
        isRunning = false
        Log.i(TAG, "AutomationScheduler stopped")
    }

    /** Used in tests to manually fire a time tick at a specific time */
    fun simulateTick(hour: Int, minute: Int) {
        triggerManager.onTimeTick(hour, minute)
    }
}
