package com.nova.mobile.sync

import android.util.Log
import com.nova.mobile.lifecycle.LifecycleManager
import kotlinx.coroutines.*
import java.time.Instant

/**
 * SyncManager — Phase 8 Main Orchestrator.
 *
 * Responsibilities:
 *   1. Manage device registry (trusted devices only)
 *   2. Trigger outbound sync when state changes
 *   3. Apply incoming payloads with conflict detection
 *   4. Manage offline queue + retry on reconnect
 *   5. Drive heartbeat loop
 *   6. Publish lifecycle events for all operations
 *   7. Enforce security: only authenticated devices sync
 *
 * No Cloud. No LLM. No credentials stored.
 */
class SyncManager(
    private val localDeviceId: String,
    private val localDeviceName: String,
    private val localPlatform: Platform,
    private val syncEngine: SyncEngine,
    private val lifecycleManager: LifecycleManager,
    conflictPolicy: ConflictPolicy = ConflictPolicy.NEWEST_WINS
) {
    companion object {
        private const val TAG = "SyncManager"
        private const val HEARTBEAT_INTERVAL_MS = 30_000L
        private const val MAX_RETRY_ATTEMPTS = 5
    }

    val deviceRegistry = DeviceRegistry()
    val repository = SyncRepository()
    val conflictResolver = ConflictResolver(conflictPolicy)

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private var heartbeatJob: Job? = null

    private var totalSent = 0
    private var totalReceived = 0
    private var lastSyncTimestamp = 0L

    // ── Lifecycle ─────────────────────────────────────────────────────────────

    fun start() {
        // Register this device
        deviceRegistry.register(
            DeviceInfo(
                deviceId = localDeviceId,
                deviceName = localDeviceName,
                platform = localPlatform,
                version = "3.0.0",
                capabilities = setOf("MEMORY_SYNC", "ROUTINE_SYNC", "SESSION_CONTINUITY"),
                status = DeviceStatus.ONLINE,
                isAuthenticated = true
            )
        )
        startHeartbeat()
        lifecycleManager.publishEvent(SyncEvent.SYNC_RESTORED.name, mapOf("device" to localDeviceName))
        Log.i(TAG, "SyncManager started for device '$localDeviceName'")
    }

    fun stop() {
        heartbeatJob?.cancel()
        scope.cancel()
        deviceRegistry.markOffline(localDeviceId)
        lifecycleManager.publishEvent(SyncEvent.DEVICE_LEFT.name, mapOf("device" to localDeviceName))
        Log.i(TAG, "SyncManager stopped")
    }

    // ── Device Management ─────────────────────────────────────────────────────

    fun registerDevice(device: DeviceInfo): Boolean {
        val ok = deviceRegistry.register(device)
        if (ok) {
            lifecycleManager.publishEvent(SyncEvent.DEVICE_JOINED.name,
                mapOf("deviceId" to device.deviceId, "name" to device.deviceName))
            Log.i(TAG, "Device joined: '${device.deviceName}' [${device.deviceId}]")
        }
        return ok
    }

    fun authenticateDevice(deviceId: String): Boolean {
        val ok = deviceRegistry.authenticate(deviceId)
        if (ok) {
            lifecycleManager.publishEvent(SyncEvent.DEVICE_AUTHENTICATED.name,
                mapOf("deviceId" to deviceId))
            // Flush offline queue to this newly authenticated device
            flushOfflineQueue(deviceId)
        }
        return ok
    }

    fun deviceLeft(deviceId: String) {
        deviceRegistry.markOffline(deviceId)
        lifecycleManager.publishEvent(SyncEvent.DEVICE_LEFT.name,
            mapOf("deviceId" to deviceId))
        Log.i(TAG, "Device went offline: $deviceId")
    }

    // ── Sync Operations ───────────────────────────────────────────────────────

    fun syncNow(targetDeviceId: String? = null): Boolean {
        val targets = if (targetDeviceId != null) {
            listOfNotNull(deviceRegistry.get(targetDeviceId)?.takeIf { it.isAuthenticated })
        } else {
            deviceRegistry.getOnline()
        }

        if (targets.isEmpty()) {
            Log.i(TAG, "No authenticated online devices to sync with — queuing")
            val payloads = syncEngine.buildOutboundPayloads()
            payloads.forEach { repository.enqueue(it) }
            return false
        }

        lifecycleManager.publishEvent(SyncEvent.SYNC_STARTED.name,
            mapOf("targets" to targets.size))

        val payloads = syncEngine.buildOutboundPayloads()
        var success = true

        targets.forEach { target ->
            try {
                payloads.forEach { payload ->
                    // Simulate dispatch — in production this goes over WebSocket/local LAN
                    Log.d(TAG, "→ Sent [${payload.category}] ${payload.key} to '${target.deviceName}'")
                    totalSent++
                }
                Log.i(TAG, "Sync complete → '${target.deviceName}' (${payloads.size} payloads)")
            } catch (e: Exception) {
                Log.e(TAG, "Sync failed → '${target.deviceName}': ${e.message}")
                payloads.forEach { repository.enqueue(it) }
                success = false
            }
        }

        lastSyncTimestamp = Instant.now().epochSecond
        val event = if (success) SyncEvent.SYNC_COMPLETED else SyncEvent.SYNC_FAILED
        lifecycleManager.publishEvent(event.name,
            mapOf("payloads" to payloads.size, "targets" to targets.size))
        return success
    }

    /** Called when a payload arrives from a remote device. */
    fun receivePayload(payload: SyncPayload): Boolean {
        if (!deviceRegistry.isAuthenticated(payload.sourceDeviceId)) {
            Log.w(TAG, "REJECTED payload from unauthenticated device: ${payload.sourceDeviceId}")
            return false
        }

        totalReceived++
        val conflict = repository.detectConflict(payload)
        if (conflict != null) {
            val resolved = conflictResolver.resolve(conflict, localPlatform)
            repository.recordConflict(resolved)
            lifecycleManager.publishEvent(SyncEvent.CONFLICT_DETECTED.name,
                mapOf("key" to conflict.key, "category" to conflict.category.name))
            if (resolved.isResolved) {
                lifecycleManager.publishEvent(SyncEvent.CONFLICT_RESOLVED.name,
                    mapOf("key" to conflict.key, "resolvedValue" to (resolved.resolvedValue ?: "")))
            }
            // Apply the resolved value
            val resolvedPayload = if (resolved.isResolved && resolved.resolvedValue != null) {
                payload.copy(value = resolved.resolvedValue)
            } else payload
            return syncEngine.applyInboundPayload(resolvedPayload, repository)
        }

        return syncEngine.applyInboundPayload(payload, repository)
    }

    // ── Session Continuity ────────────────────────────────────────────────────

    fun startSession(taskDescription: String, originDeviceId: String): SyncSession {
        val session = SyncSession(
            originDeviceId = originDeviceId,
            currentDeviceId = localDeviceId,
            taskDescription = taskDescription
        )
        repository.saveSession(session)
        Log.i(TAG, "Session started: '${taskDescription}' [${session.sessionId}]")
        return session
    }

    fun handoffSession(sessionId: String, targetDeviceId: String): Boolean {
        val session = repository.getSession(sessionId) ?: return false
        val updated = session.copy(
            currentDeviceId = targetDeviceId,
            updatedAt = Instant.now().epochSecond
        )
        repository.saveSession(updated)
        Log.i(TAG, "Session '${session.taskDescription}' handed off → $targetDeviceId")
        return true
    }

    // ── Offline Queue ─────────────────────────────────────────────────────────

    private fun flushOfflineQueue(deviceId: String) {
        val queued = repository.drainQueue()
        if (queued.isEmpty()) return
        Log.i(TAG, "Flushing ${queued.size} queued payloads to device $deviceId")
        queued.forEach { payload ->
            Log.d(TAG, "→ Flushed [${payload.category}] ${payload.key}")
        }
    }

    // ── Heartbeat ─────────────────────────────────────────────────────────────

    private fun startHeartbeat() {
        heartbeatJob = scope.launch {
            while (isActive) {
                delay(HEARTBEAT_INTERVAL_MS)
                deviceRegistry.updateHeartbeat(localDeviceId)
                Log.d(TAG, "Heartbeat [${deviceRegistry.countOnline()} online devices]")
            }
        }
    }

    // ── Stats ─────────────────────────────────────────────────────────────────

    fun getStats(): SyncStats = SyncStats(
        totalPayloadsSent = totalSent,
        totalPayloadsReceived = totalReceived,
        totalConflictsDetected = repository.getConflicts().size,
        totalConflictsResolved = repository.getConflicts().count { it.isResolved },
        lastSyncTimestamp = lastSyncTimestamp,
        pendingQueueSize = repository.queueSize(),
        connectedDevices = deviceRegistry.countOnline()
    )
}
