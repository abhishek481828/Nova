package com.nova.mobile.hybrid

import android.util.Log

/**
 * ExecutionPlanner — Builds an execution plan for a given request.
 * Selects the target, defines timeout + retry policy, and plans fallback.
 */
data class ExecutionPlan(
    val requestId: String,
    val rawText: String,
    val intentName: String,
    val primaryTarget: ExecutionTarget,
    val fallbackTarget: ExecutionTarget?,
    val timeoutMs: Long,
    val maxRetries: Int,
    val requiresNovaCoreButOffline: Boolean
)

class ExecutionPlanner(private val routingEngine: RoutingEngine) {
    companion object {
        private const val TAG = "ExecutionPlanner"
        private const val LOCAL_TIMEOUT_MS = 5000L
        private const val CORE_TIMEOUT_MS = 15000L
        private const val MAX_RETRIES = 2
    }

    fun plan(intentName: String, rawText: String): ExecutionPlan {
        val requestId = java.util.UUID.randomUUID().toString()
        val target = routingEngine.decide(intentName, rawText)
        val coreRequiredButOffline = routingEngine.requiresNovaCoreButOffline(intentName, rawText)

        val plan = ExecutionPlan(
            requestId = requestId,
            rawText = rawText,
            intentName = intentName,
            primaryTarget = target,
            fallbackTarget = if (target == ExecutionTarget.NOVA_CORE) ExecutionTarget.LOCAL_ANDROID else null,
            timeoutMs = if (target == ExecutionTarget.NOVA_CORE) CORE_TIMEOUT_MS else LOCAL_TIMEOUT_MS,
            maxRetries = if (target == ExecutionTarget.NOVA_CORE) MAX_RETRIES else 0,
            requiresNovaCoreButOffline = coreRequiredButOffline
        )
        Log.i(TAG, "Planned: intent=$intentName, target=$target, fallback=${plan.fallbackTarget}, coreOffline=$coreRequiredButOffline")
        return plan
    }
}
