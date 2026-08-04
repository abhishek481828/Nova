package com.nova.mobile.hybrid

/**
 * ExecutionContext — Temporary session context shared between routing decisions.
 * Carries current request info, previous intent, session ID, and device state.
 * Supports context synchronization with Nova Core (no long-term memory yet).
 */
data class ExecutionContext(
    val sessionId: String = java.util.UUID.randomUUID().toString(),
    val currentRequest: String = "",
    val previousRequest: String = "",
    val previousTarget: ExecutionTarget = ExecutionTarget.UNKNOWN,
    val activeTask: String = "",
    val deviceBatteryLevel: Int = 100,
    val isDeviceOnline: Boolean = true,
    val novaCoreAvailable: Boolean = false
) {
    fun withRequest(request: String): ExecutionContext =
        copy(previousRequest = currentRequest, previousTarget = previousTarget, currentRequest = request)
}
