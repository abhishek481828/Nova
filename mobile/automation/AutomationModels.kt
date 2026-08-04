package com.nova.mobile.automation

import java.time.Instant

data class AutomationTrigger(
    val type: TriggerType,
    val voicePhrase: String? = null,      // for VOICE_COMMAND trigger
    val timeHour: Int? = null,            // for TIME trigger (0-23)
    val timeMinute: Int? = null,          // for TIME trigger (0-59)
    val daysOfWeek: Set<Int> = emptySet(),// 1=Mon … 7=Sun
    val batteryThreshold: Int? = null,    // for BATTERY_LOW/HIGH
    val bluetoothDevice: String? = null,  // for BLUETOOTH_CONNECTED
    val wifiSsid: String? = null,         // for WIFI_CONNECTED
    val appPackage: String? = null        // for APP_OPENED
)

data class AutomationCondition(
    val type: ConditionType,
    val intValue: Int? = null,            // e.g. battery percentage
    val startTime: String? = null,        // "HH:mm" for TIME_RANGE
    val endTime: String? = null
)

data class AutomationAction(
    val type: ActionType,
    val params: Map<String, String> = emptyMap(),  // e.g. {"contact": "Pankaj", "message": "..."}
    val delaySecondsAfter: Int = 0        // delay before next action
)

data class Routine(
    val id: String = java.util.UUID.randomUUID().toString(),
    val name: String,
    val description: String = "",
    val trigger: AutomationTrigger,
    val conditions: List<AutomationCondition> = emptyList(),
    val actions: List<AutomationAction>,
    val status: AutomationStatus = AutomationStatus.ENABLED,
    val requiresConfirmation: Boolean = false,
    val createdAt: Long = Instant.now().epochSecond,
    val updatedAt: Long = Instant.now().epochSecond,
    val lastExecutedAt: Long? = null,
    val executionCount: Int = 0
)

data class AutomationResult(
    val routineId: String,
    val routineName: String,
    val isSuccess: Boolean,
    val executedActions: List<String> = emptyList(),
    val failedAction: String? = null,
    val errorMessage: String? = null,
    val executionTimeMs: Long = 0L,
    val triggeredAt: Long = Instant.now().epochSecond
)
