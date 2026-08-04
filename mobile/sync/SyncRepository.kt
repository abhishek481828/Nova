package com.nova.mobile.sync

import android.util.Log
import java.time.Instant

/**
 * SyncRepository — Stores sync state, offline queue, and conflict history.
 *
 * Offline queue: payloads that couldn't be sent are queued here
 * and flushed when connectivity is restored.
 */
class SyncRepository {
    companion object {
        private const val TAG = "SyncRepository"
        private const val MAX_QUEUE_SIZE = 500
    }

    // Local sync state: category → key → payload
    private val syncState: MutableMap<SyncCategory, MutableMap<String, SyncPayload>> =
        SyncCategory.values().associateWith { mutableMapOf<String, SyncPayload>() }.toMutableMap()

    // Offline outbound queue
    private val offlineQueue: ArrayDeque<SyncPayload> = ArrayDeque()

    // Conflict history
    private val conflictHistory: MutableList<SyncConflict> = mutableListOf()

    // Sync sessions
    private val sessions: MutableMap<String, SyncSession> = mutableMapOf()

    // ── Sync State ───────────────────────────────────────────────────────────

    fun put(payload: SyncPayload): Boolean {
        val existing = syncState[payload.category]?.get(payload.key)
        return if (existing == null || payload.timestamp >= existing.timestamp) {
            syncState.getOrPut(payload.category) { mutableMapOf() }[payload.key] = payload
            true
        } else {
            false  // existing is newer — caller should handle as conflict
        }
    }

    fun get(category: SyncCategory, key: String): SyncPayload? =
        syncState[category]?.get(key)

    fun getAll(category: SyncCategory): List<SyncPayload> =
        syncState[category]?.values?.toList() ?: emptyList()

    fun getAllPayloads(): List<SyncPayload> =
        syncState.values.flatMap { it.values }

    fun detectConflict(incoming: SyncPayload): SyncConflict? {
        val existing = syncState[incoming.category]?.get(incoming.key) ?: return null
        if (existing.value == incoming.value) return null   // no actual conflict
        if (existing.sourceDeviceId == incoming.sourceDeviceId) return null
        return SyncConflict(
            category = incoming.category,
            key = incoming.key,
            localValue = existing.value,
            remoteValue = incoming.value,
            localTimestamp = existing.timestamp,
            remoteTimestamp = incoming.timestamp,
            localDeviceId = existing.sourceDeviceId,
            remoteDeviceId = incoming.sourceDeviceId
        )
    }

    // ── Offline Queue ─────────────────────────────────────────────────────────

    fun enqueue(payload: SyncPayload): Boolean {
        if (offlineQueue.size >= MAX_QUEUE_SIZE) {
            Log.w(TAG, "Offline queue full — dropping oldest payload")
            offlineQueue.removeFirst()
        }
        offlineQueue.addLast(payload)
        return true
    }

    fun drainQueue(): List<SyncPayload> {
        val drained = offlineQueue.toList()
        offlineQueue.clear()
        Log.i(TAG, "Drained ${drained.size} payloads from offline queue")
        return drained
    }

    fun queueSize(): Int = offlineQueue.size

    // ── Conflicts ─────────────────────────────────────────────────────────────

    fun recordConflict(conflict: SyncConflict) {
        conflictHistory.add(conflict)
        if (conflictHistory.size > 200) conflictHistory.removeAt(0)
    }

    fun getConflicts(): List<SyncConflict> = conflictHistory.toList()

    fun getUnresolved(): List<SyncConflict> = conflictHistory.filter { !it.isResolved }

    // ── Sessions ──────────────────────────────────────────────────────────────

    fun saveSession(session: SyncSession) { sessions[session.sessionId] = session }

    fun getSession(sessionId: String): SyncSession? = sessions[sessionId]

    fun getActiveSessions(): List<SyncSession> = sessions.values.filter { it.isActive }

    fun closeSession(sessionId: String): Boolean {
        val s = sessions[sessionId] ?: return false
        sessions[sessionId] = s.copy(isActive = false, updatedAt = Instant.now().epochSecond)
        return true
    }

    fun totalCount(): Int = getAllPayloads().size
}
