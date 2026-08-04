package com.nova.mobile.hybrid

import android.util.Log
import com.nova.mobile.command.BuiltInIntent

/**
 * RoutingEngine — The core decision maker.
 * Combines CapabilityResolver + DeviceDiscovery + RoutingPolicy
 * to decide where each request should be executed.
 */
class RoutingEngine(
    private val capabilityResolver: CapabilityResolver,
    private val deviceDiscovery: DeviceDiscovery,
    var policy: RoutingPolicy = RoutingPolicy.AUTOMATIC
) {
    companion object {
        private const val TAG = "RoutingEngine"
    }

    fun decide(intentName: String, rawText: String): ExecutionTarget {
        return when (policy) {
            RoutingPolicy.ALWAYS_LOCAL -> {
                Log.i(TAG, "Policy=ALWAYS_LOCAL → LOCAL_ANDROID")
                ExecutionTarget.LOCAL_ANDROID
            }

            RoutingPolicy.ALWAYS_NOVA_CORE -> {
                val target = if (deviceDiscovery.isNovaCoreOnline) {
                    ExecutionTarget.NOVA_CORE
                } else {
                    Log.w(TAG, "Policy=ALWAYS_NOVA_CORE but Core offline → fallback to LOCAL")
                    ExecutionTarget.LOCAL_ANDROID
                }
                target
            }

            RoutingPolicy.OFFLINE_MODE -> {
                Log.i(TAG, "Policy=OFFLINE_MODE → LOCAL_ANDROID enforced")
                ExecutionTarget.LOCAL_ANDROID
            }

            RoutingPolicy.FALLBACK -> {
                // Try Nova Core first, fallback to local if offline
                if (capabilityResolver.isNovaCoreRequired(rawText) && deviceDiscovery.isNovaCoreOnline) {
                    ExecutionTarget.NOVA_CORE
                } else {
                    ExecutionTarget.LOCAL_ANDROID
                }
            }

            RoutingPolicy.AUTOMATIC -> {
                val preferredTarget = capabilityResolver.resolveTarget(intentName, rawText)
                return when {
                    preferredTarget == ExecutionTarget.NOVA_CORE && deviceDiscovery.isNovaCoreOnline -> {
                        Log.i(TAG, "AUTOMATIC → NOVA_CORE (online, capability match)")
                        ExecutionTarget.NOVA_CORE
                    }
                    preferredTarget == ExecutionTarget.NOVA_CORE && !deviceDiscovery.isNovaCoreOnline -> {
                        Log.w(TAG, "AUTOMATIC → Core required but OFFLINE. Staying on LOCAL for degraded response.")
                        ExecutionTarget.LOCAL_ANDROID
                    }
                    else -> {
                        Log.i(TAG, "AUTOMATIC → LOCAL_ANDROID")
                        ExecutionTarget.LOCAL_ANDROID
                    }
                }
            }
        }
    }

    fun requiresNovaCoreButOffline(intentName: String, rawText: String): Boolean {
        val preferred = capabilityResolver.resolveTarget(intentName, rawText)
        return preferred == ExecutionTarget.NOVA_CORE && !deviceDiscovery.isNovaCoreOnline
    }
}
