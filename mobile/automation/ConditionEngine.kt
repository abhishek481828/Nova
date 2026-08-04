package com.nova.mobile.automation

import android.util.Log

/**
 * ConditionEngine — Evaluates whether all pre-conditions for a routine are met.
 * Conditions are checked BEFORE actions are executed.
 */
class ConditionEngine {
    companion object {
        private const val TAG = "ConditionEngine"
    }

    // Device state (injected/updated by system receivers)
    var batteryLevel: Int = 100
    var isCharging: Boolean = false
    var isHeadphonesConnected: Boolean = false
    var isWifiConnected: Boolean = false
    var isScreenLocked: Boolean = false
    var isNovaCoreOnline: Boolean = false

    fun evaluate(conditions: List<AutomationCondition>): Boolean {
        for (condition in conditions) {
            val passed = evaluateSingle(condition)
            if (!passed) {
                Log.i(TAG, "Condition NOT met: ${condition.type} → routine blocked")
                return false
            }
        }
        return true
    }

    private fun evaluateSingle(condition: AutomationCondition): Boolean {
        return when (condition.type) {
            ConditionType.BATTERY_ABOVE -> batteryLevel > (condition.intValue ?: 20)
            ConditionType.BATTERY_BELOW -> batteryLevel < (condition.intValue ?: 20)
            ConditionType.WIFI_CONNECTED -> isWifiConnected
            ConditionType.CHARGING -> isCharging
            ConditionType.HEADPHONES_CONNECTED -> isHeadphonesConnected
            ConditionType.SCREEN_LOCKED -> isScreenLocked
            ConditionType.SCREEN_UNLOCKED -> !isScreenLocked
            ConditionType.NOVA_CORE_ONLINE -> isNovaCoreOnline
            ConditionType.TIME_RANGE -> isWithinTimeRange(condition.startTime, condition.endTime)
        }
    }

    private fun isWithinTimeRange(start: String?, end: String?): Boolean {
        if (start == null || end == null) return true
        return try {
            val now = java.time.LocalTime.now()
            val s = java.time.LocalTime.parse(start)
            val e = java.time.LocalTime.parse(end)
            now.isAfter(s) && now.isBefore(e)
        } catch (ex: Exception) {
            Log.w(TAG, "Invalid time range: $start – $end")
            false
        }
    }
}
