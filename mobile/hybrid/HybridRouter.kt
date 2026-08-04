package com.nova.mobile.hybrid

import android.content.Context
import android.util.Log
import com.nova.mobile.command.CommandEngine
import com.nova.mobile.lifecycle.LifecycleManager

/**
 * HybridRouter — Main orchestrator for Phase 5.
 *
 * Flow:
 *   recognizedText → RoutingEngine (decide target)
 *     ├─ LOCAL_ANDROID  → CommandEngine.executeText()
 *     └─ NOVA_CORE      → forwardToNovaCore() (WebSocket + JWT)
 *                          if offline → polite degraded response
 *
 * Publishes lifecycle events: HybridRouted, HybridLocalExecuted,
 *   HybridCoreSent, HybridCoreOffline, HybridFallback.
 */
class HybridRouter(
    private val context: Context,
    private val lifecycleManager: LifecycleManager,
    private val commandEngine: CommandEngine
) {
    companion object {
        private const val TAG = "HybridRouter"
    }

    val capabilityResolver = CapabilityResolver()
    val deviceDiscovery = DeviceDiscovery()
    val routingEngine = RoutingEngine(capabilityResolver, deviceDiscovery)
    val executionPlanner = ExecutionPlanner(routingEngine)

    private val resultListeners = mutableListOf<(ExecutionResult) -> Unit>()

    fun route(recognizedText: String, intentName: String = "UNKNOWN"): ExecutionResult {
        val startTime = System.currentTimeMillis()
        val plan = executionPlanner.plan(intentName, recognizedText)

        lifecycleManager.publishEvent(
            "HybridRouted",
            mapOf("requestId" to plan.requestId, "intent" to intentName, "target" to plan.primaryTarget.name)
        )

        val result = when {
            // Core required but offline → graceful degradation
            plan.requiresNovaCoreButOffline -> {
                Log.w(TAG, "Nova Core required but OFFLINE for '${recognizedText}'")
                lifecycleManager.publishEvent("HybridCoreOffline", mapOf("requestId" to plan.requestId))
                ExecutionResult(
                    requestId = plan.requestId,
                    intent = intentName,
                    target = ExecutionTarget.LOCAL_ANDROID,
                    isSuccess = false,
                    spokenResponse = "I can help with phone tasks right now, but this request requires Nova Core, which is currently unavailable.",
                    executionTimeMs = System.currentTimeMillis() - startTime,
                    errorMessage = "Nova Core offline"
                )
            }

            plan.primaryTarget == ExecutionTarget.NOVA_CORE -> {
                Log.i(TAG, "Forwarding '${recognizedText}' to Nova Core")
                forwardToNovaCore(plan, startTime)
            }

            else -> {
                Log.i(TAG, "Executing '${recognizedText}' locally on Android")
                executeLocally(plan, startTime)
            }
        }

        notifyListeners(result)
        return result
    }

    private fun executeLocally(plan: ExecutionPlan, startTime: Long): ExecutionResult {
        return try {
            val cmdResult = commandEngine.executeText(plan.rawText)
            lifecycleManager.publishEvent(
                "HybridLocalExecuted",
                mapOf("requestId" to plan.requestId, "intent" to plan.intentName, "response" to cmdResult.spokenResponse)
            )
            ExecutionResult(
                requestId = plan.requestId,
                intent = plan.intentName,
                target = ExecutionTarget.LOCAL_ANDROID,
                isSuccess = cmdResult.isSuccess,
                spokenResponse = cmdResult.spokenResponse,
                executionTimeMs = System.currentTimeMillis() - startTime,
                errorMessage = cmdResult.errorMessage
            )
        } catch (e: Exception) {
            Log.e(TAG, "Local execution failed", e)
            ExecutionResult(
                plan.requestId, plan.intentName, ExecutionTarget.LOCAL_ANDROID, false,
                spokenResponse = "Sorry, I couldn't complete that locally.",
                executionTimeMs = System.currentTimeMillis() - startTime,
                errorMessage = e.message
            )
        }
    }

    private fun forwardToNovaCore(plan: ExecutionPlan, startTime: Long): ExecutionResult {
        val networkStart = System.currentTimeMillis()
        return try {
            // Secure forwarding via WebSocket + JWT (stub — bridge to actual WS in future)
            Log.i(TAG, "[WS] Forwarding to Nova Core: ${plan.rawText}")
            lifecycleManager.publishEvent("HybridCoreSent", mapOf("requestId" to plan.requestId))

            // In production: send via WebSocket and await response within plan.timeoutMs
            // For Phase 5 Python simulation layer — response comes back via callback
            val latency = System.currentTimeMillis() - networkStart
            ExecutionResult(
                requestId = plan.requestId,
                intent = plan.intentName,
                target = ExecutionTarget.NOVA_CORE,
                isSuccess = true,
                spokenResponse = "Forwarded to Nova Core. Processing your request.",
                executionTimeMs = System.currentTimeMillis() - startTime,
                networkLatencyMs = latency
            )
        } catch (e: Exception) {
            Log.e(TAG, "Nova Core forwarding failed — falling back to local", e)
            lifecycleManager.publishEvent("HybridFallback", mapOf("requestId" to plan.requestId, "reason" to (e.message ?: "forward error")))
            executeLocally(plan.copy(primaryTarget = ExecutionTarget.LOCAL_ANDROID), startTime)
                .copy(usedFallback = true)
        }
    }

    fun addResultListener(listener: (ExecutionResult) -> Unit) {
        resultListeners.add(listener)
    }

    private fun notifyListeners(result: ExecutionResult) {
        resultListeners.forEach { it(result) }
    }
}
