package com.nova.mobile.sync

import java.time.Instant

data class DeviceInfo(
    val deviceId: String,
    val deviceName: String,
    val platform: Platform,
    val version: String,
    val capabilities: Set<String> = emptySet(),
    val lastSeen: Long = Instant.now().epochSecond,
    val status: DeviceStatus = DeviceStatus.UNAUTHENTICATED,
    val isAuthenticated: Boolean = false,
    val healthScore: Float = 1.0f
)

data class SyncPayload(
    val payloadId: String = java.util.UUID.randomUUID().toString(),
    val category: SyncCategory,
    val key: String,
    val value: String,
    val sourceDeviceId: String,
    val timestamp: Long = Instant.now().epochSecond,
    val checksum: String = ""  // sha256 of value for integrity verification
)

data class SyncConflict(
    val conflictId: String = java.util.UUID.randomUUID().toString(),
    val category: SyncCategory,
    val key: String,
    val localValue: String,
    val remoteValue: String,
    val localTimestamp: Long,
    val remoteTimestamp: Long,
    val localDeviceId: String,
    val remoteDeviceId: String,
    val resolvedValue: String? = null,
    val isResolved: Boolean = false,
    val detectedAt: Long = Instant.now().epochSecond
)

data class SyncSession(
    val sessionId: String = java.util.UUID.randomUUID().toString(),
    val originDeviceId: String,
    val currentDeviceId: String,
    val taskDescription: String,
    val contextSnapshot: Map<String, String> = emptyMap(),
    val createdAt: Long = Instant.now().epochSecond,
    val updatedAt: Long = Instant.now().epochSecond,
    val isActive: Boolean = true
)

data class SyncStats(
    val totalPayloadsSent: Int = 0,
    val totalPayloadsReceived: Int = 0,
    val totalConflictsDetected: Int = 0,
    val totalConflictsResolved: Int = 0,
    val lastSyncTimestamp: Long = 0L,
    val pendingQueueSize: Int = 0,
    val connectedDevices: Int = 0
)
