package com.nova.mobile.sync

import android.util.Log

/**
 * ConflictResolver — Resolves sync conflicts between devices.
 *
 * Supported policies:
 *   NEWEST_WINS     — Most recently updated value wins (default)
 *   OLDEST_WINS     — First value set wins
 *   PHONE_WINS      — Android device always wins
 *   NOVA_CORE_WINS  — Laptop always wins
 *   USER_CONFIRM    — Conflict queued for user decision
 *
 * Sensitive keys (token, password, otp, secret) are NEVER sync-resolved.
 */
class ConflictResolver(var policy: ConflictPolicy = ConflictPolicy.NEWEST_WINS) {
    companion object {
        private const val TAG = "ConflictResolver"
        private val BLOCKED_KEYS = setOf("password", "token", "otp", "secret", "private_key", "auth")
    }

    private val pendingUserConfirmations: MutableList<SyncConflict> = mutableListOf()

    fun resolve(conflict: SyncConflict, localDevicePlatform: Platform): SyncConflict {
        if (BLOCKED_KEYS.any { conflict.key.lowercase().contains(it) }) {
            Log.e(TAG, "BLOCKED: Refusing to resolve sensitive key '${conflict.key}'")
            return conflict.copy(isResolved = false)
        }

        val resolvedValue = when (policy) {
            ConflictPolicy.NEWEST_WINS ->
                if (conflict.remoteTimestamp >= conflict.localTimestamp)
                    conflict.remoteValue else conflict.localValue

            ConflictPolicy.OLDEST_WINS ->
                if (conflict.localTimestamp <= conflict.remoteTimestamp)
                    conflict.localValue else conflict.remoteValue

            ConflictPolicy.PHONE_WINS ->
                if (localDevicePlatform == Platform.ANDROID) conflict.localValue
                else conflict.remoteValue

            ConflictPolicy.NOVA_CORE_WINS ->
                if (localDevicePlatform == Platform.NOVA_CORE) conflict.localValue
                else conflict.remoteValue

            ConflictPolicy.USER_CONFIRM -> {
                pendingUserConfirmations.add(conflict)
                Log.i(TAG, "Conflict queued for user confirmation: ${conflict.key}")
                return conflict.copy(isResolved = false)
            }
        }

        Log.i(TAG, "Conflict resolved [${policy.name}]: '${conflict.key}' → '$resolvedValue'")
        return conflict.copy(resolvedValue = resolvedValue, isResolved = true)
    }

    fun resolveByUser(conflictId: String, chosenValue: String): SyncConflict? {
        val idx = pendingUserConfirmations.indexOfFirst { it.conflictId == conflictId }
        if (idx < 0) return null
        val resolved = pendingUserConfirmations.removeAt(idx).copy(
            resolvedValue = chosenValue, isResolved = true
        )
        Log.i(TAG, "Conflict resolved by user: '${resolved.key}' → '$chosenValue'")
        return resolved
    }

    fun getPendingConfirmations(): List<SyncConflict> = pendingUserConfirmations.toList()

    fun pendingCount(): Int = pendingUserConfirmations.size
}
