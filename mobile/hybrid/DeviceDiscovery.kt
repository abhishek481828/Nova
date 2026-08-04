package com.nova.mobile.hybrid

import android.util.Log
import kotlinx.coroutines.*
import java.net.InetSocketAddress
import java.net.Socket

/**
 * DeviceDiscovery — Continuously monitors Nova Core (laptop) availability.
 * Checks TCP reachability, tracks latency, and fires callbacks on state changes.
 * Supports auto-reconnect.
 */
class DeviceDiscovery {
    companion object {
        private const val TAG = "DeviceDiscovery"
        private const val PROBE_INTERVAL_MS = 5000L
        private const val PROBE_TIMEOUT_MS = 1500
        private const val DEFAULT_HOST = "192.168.1.100"
        private const val DEFAULT_PORT = 8765
    }

    var host: String = DEFAULT_HOST
    var port: Int = DEFAULT_PORT

    var isNovaCoreOnline: Boolean = false
        private set
    var lastLatencyMs: Long = -1L
        private set
    var consecutiveFailures: Int = 0
        private set

    private val listeners = mutableListOf<(Boolean) -> Unit>()
    private var probeJob: Job? = null

    fun startProbing(scope: CoroutineScope = CoroutineScope(Dispatchers.IO)) {
        probeJob = scope.launch {
            while (isActive) {
                val (reachable, latency) = probe()
                val changed = reachable != isNovaCoreOnline
                isNovaCoreOnline = reachable
                lastLatencyMs = latency
                if (reachable) consecutiveFailures = 0 else consecutiveFailures++
                if (changed) {
                    Log.i(TAG, "Nova Core state changed: ${if (reachable) "ONLINE" else "OFFLINE"} (latency=${latency}ms)")
                    notifyListeners(reachable)
                }
                delay(PROBE_INTERVAL_MS)
            }
        }
    }

    fun stopProbing() {
        probeJob?.cancel()
        probeJob = null
    }

    fun checkNow(): Boolean {
        val (reachable, latency) = probe()
        isNovaCoreOnline = reachable
        lastLatencyMs = latency
        return reachable
    }

    fun addStateListener(listener: (Boolean) -> Unit) {
        listeners.add(listener)
    }

    private fun probe(): Pair<Boolean, Long> {
        return try {
            val start = System.currentTimeMillis()
            Socket().use { socket ->
                socket.connect(InetSocketAddress(host, port), PROBE_TIMEOUT_MS)
            }
            val elapsed = System.currentTimeMillis() - start
            Pair(true, elapsed)
        } catch (e: Exception) {
            Pair(false, -1L)
        }
    }

    private fun notifyListeners(isOnline: Boolean) {
        listeners.forEach { it(isOnline) }
    }
}
