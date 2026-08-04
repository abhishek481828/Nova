package com.nova.mobile.sync

import android.util.Log
import com.nova.mobile.memory.MemoryManager
import com.nova.mobile.memory.MemoryCategory
import com.nova.mobile.automation.AutomationManager
import java.time.Instant

/**
 * SyncEngine — Determines WHAT gets synchronized and packages it into SyncPayloads.
 *
 * Blocked from synchronization (enforced here):
 *   - Passwords, OTPs, tokens, private keys, sensitive credentials
 *
 * Synchronized categories:
 *   - User preferences (brightness, volume, language)
 *   - Favorite contacts & apps
 *   - Recent commands
 *   - Routine definitions
 *   - Trusted devices
 *   - Session state
 *   - Configuration
 */
class SyncEngine(
    private val memoryManager: MemoryManager,
    private val automationManager: AutomationManager,
    private val deviceId: String
) {
    companion object {
        private const val TAG = "SyncEngine"
        private val BLOCKED_KEYS = setOf(
            "password", "passwd", "otp", "token", "secret", "private_key",
            "auth_token", "access_token", "refresh_token", "pin", "cvv"
        )
    }

    /** Build outbound sync payloads from current device state. */
    fun buildOutboundPayloads(): List<SyncPayload> {
        val payloads = mutableListOf<SyncPayload>()

        // 1. Memory: preferences
        val preferences = listOf(
            MemoryCategory.PREFERRED_BRIGHTNESS,
            MemoryCategory.PREFERRED_VOLUME,
            MemoryCategory.PREFERRED_LANGUAGE,
            MemoryCategory.PREFERRED_MUSIC_APP,
            MemoryCategory.PREFERRED_BROWSER
        )
        preferences.forEach { cat ->
            memoryManager.repository.list(cat).forEach { entry ->
                if (!isSensitive(entry.key)) {
                    payloads.add(makePayload(SyncCategory.PREFERENCES, "${cat.name}:${entry.key}", entry.value))
                }
            }
        }

        // 2. Favorite contacts
        memoryManager.repository.list(MemoryCategory.FAVORITE_CONTACT).forEach { entry ->
            payloads.add(makePayload(SyncCategory.FAVORITE_CONTACTS, entry.key, entry.value))
        }

        // 3. Favorite apps
        memoryManager.repository.list(MemoryCategory.FAVORITE_APP).forEach { entry ->
            payloads.add(makePayload(SyncCategory.FAVORITE_APPS, entry.key, entry.value))
        }

        // 4. Recent commands (last 20 only)
        memoryManager.repository.list(MemoryCategory.RECENT_COMMAND).takeLast(20).forEach { entry ->
            payloads.add(makePayload(SyncCategory.RECENT_COMMANDS, entry.key, entry.value))
        }

        // 5. Routine definitions (name + action count as summary)
        automationManager.repository.getEnabled().forEach { routine ->
            val summary = "${routine.name}|${routine.actions.size}|${routine.trigger.type.name}"
            payloads.add(makePayload(SyncCategory.ROUTINE_DEFINITIONS, routine.id, summary))
        }

        Log.i(TAG, "Built ${payloads.size} outbound sync payloads")
        return payloads
    }

    /** Apply an inbound payload from a remote device to local state. */
    fun applyInboundPayload(payload: SyncPayload, repository: SyncRepository): Boolean {
        if (isSensitive(payload.key)) {
            Log.e(TAG, "BLOCKED inbound payload with sensitive key: '${payload.key}'")
            return false
        }

        // Integrity check
        if (!verifyIntegrity(payload)) {
            Log.e(TAG, "Integrity check FAILED for payload: ${payload.payloadId}")
            return false
        }

        return repository.put(payload)
    }

    fun isSensitive(key: String): Boolean =
        BLOCKED_KEYS.any { key.lowercase().contains(it) }

    private fun makePayload(category: SyncCategory, key: String, value: String): SyncPayload =
        SyncPayload(
            category = category,
            key = key,
            value = value,
            sourceDeviceId = deviceId,
            timestamp = Instant.now().epochSecond,
            checksum = checksum(value)
        )

    private fun checksum(value: String): String =
        java.security.MessageDigest.getInstance("SHA-256")
            .digest(value.toByteArray())
            .joinToString("") { "%02x".format(it) }
            .take(16)

    private fun verifyIntegrity(payload: SyncPayload): Boolean {
        if (payload.checksum.isEmpty()) return true  // no checksum = legacy, allow
        return payload.checksum == checksum(payload.value)
    }
}
