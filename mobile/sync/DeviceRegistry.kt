package com.nova.mobile.sync

import android.util.Log
import java.time.Instant

/**
 * DeviceRegistry — Manages trusted devices in the Nova ecosystem.
 *
 * Rules:
 *   - Devices must be authenticated before sync is allowed.
 *   - No credentials, tokens, or private keys are stored here.
 *   - Audit log maintained for all registration events.
 */
class DeviceRegistry {
    companion object { private const val TAG = "DeviceRegistry" }

    private val devices: MutableMap<String, DeviceInfo> = mutableMapOf()
    private val auditLog: MutableList<String> = mutableListOf()

    fun register(device: DeviceInfo): Boolean {
        return try {
            devices[device.deviceId] = device
            audit("REGISTERED device='${device.deviceName}' platform=${device.platform} id=${device.deviceId}")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to register device: ${e.message}")
            false
        }
    }

    fun authenticate(deviceId: String): Boolean {
        val device = devices[deviceId] ?: return false
        devices[deviceId] = device.copy(
            isAuthenticated = true,
            status = DeviceStatus.AUTHENTICATED,
            lastSeen = Instant.now().epochSecond
        )
        audit("AUTHENTICATED device='${device.deviceName}' id=$deviceId")
        return true
    }

    fun revokeAuthentication(deviceId: String): Boolean {
        val device = devices[deviceId] ?: return false
        devices[deviceId] = device.copy(
            isAuthenticated = false,
            status = DeviceStatus.UNAUTHENTICATED
        )
        audit("REVOKED device='${device.deviceName}' id=$deviceId")
        return true
    }

    fun updateHeartbeat(deviceId: String) {
        devices[deviceId]?.let {
            devices[deviceId] = it.copy(
                lastSeen = Instant.now().epochSecond,
                status = DeviceStatus.ONLINE
            )
        }
    }

    fun markOffline(deviceId: String) {
        devices[deviceId]?.let {
            devices[deviceId] = it.copy(status = DeviceStatus.OFFLINE)
            audit("OFFLINE device='${it.deviceName}' id=$deviceId")
        }
    }

    fun get(deviceId: String): DeviceInfo? = devices[deviceId]

    fun getAll(): List<DeviceInfo> = devices.values.toList()

    fun getAuthenticated(): List<DeviceInfo> = devices.values.filter { it.isAuthenticated }

    fun getOnline(): List<DeviceInfo> = devices.values.filter {
        it.isAuthenticated && it.status == DeviceStatus.ONLINE
    }

    fun isAuthenticated(deviceId: String): Boolean =
        devices[deviceId]?.isAuthenticated == true

    fun remove(deviceId: String): Boolean {
        val device = devices.remove(deviceId) ?: return false
        audit("REMOVED device='${device.deviceName}' id=$deviceId")
        return true
    }

    fun getAuditLog(): List<String> = auditLog.toList()

    fun count(): Int = devices.size

    fun countOnline(): Int = getOnline().size

    private fun audit(message: String) {
        val entry = "[${Instant.now()}] $message"
        auditLog.add(entry)
        Log.i(TAG, entry)
        // Keep last 500 audit entries
        if (auditLog.size > 500) auditLog.removeAt(0)
    }
}
