package com.nova.companion.transport

import android.util.Log
import com.nova.companion.plugins.ActionRegistry
import com.nova.companion.plugins.hardware.DeviceInfoHandler
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.*
import okio.ByteString
import org.json.JSONObject
import java.util.concurrent.TimeUnit
import kotlin.math.min
import kotlin.math.pow
import kotlin.random.Random

enum class ConnectionState {
    DISCONNECTED,
    CONNECTING,
    AUTHENTICATED,
    RECONNECTING,
    FAILED
}

class WebSocketClientManager(
    private val actionRegistry: ActionRegistry? = null,
    private val deviceInfoHandler: DeviceInfoHandler? = null
) {
    private val client = OkHttpClient.Builder()
        .readTimeout(0, TimeUnit.MILLISECONDS)
        .writeTimeout(10, TimeUnit.SECONDS)
        .pingInterval(15, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    
    private val _connectionState = MutableStateFlow(ConnectionState.DISCONNECTED)
    val connectionState: StateFlow<ConnectionState> = _connectionState.asStateFlow()

    private var currentServerUrl: String? = null
    private var currentToken: String? = null
    private var currentDeviceId: String? = null

    private var reconnectAttempt = 0
    private var heartbeatJob: Job? = null
    private var reconnectJob: Job? = null

    fun connect(serverUrl: String, token: String, deviceId: String) {
        currentServerUrl = serverUrl
        currentToken = token
        currentDeviceId = deviceId
        reconnectAttempt = 0
        
        doConnect()
    }

    private fun doConnect() {
        val serverUrl = currentServerUrl ?: return
        val token = currentToken ?: return
        val deviceId = currentDeviceId ?: return

        _connectionState.value = if (reconnectAttempt > 0) ConnectionState.RECONNECTING else ConnectionState.CONNECTING

        val urlWithParams = if (serverUrl.contains("?")) {
            "$serverUrl&token=$token&device_id=$deviceId"
        } else {
            "$serverUrl?token=$token&device_id=$deviceId"
        }

        Log.i("WebSocketManager", "Connecting to $urlWithParams (Attempt #$reconnectAttempt)")
        val request = Request.Builder().url(urlWithParams).build()

        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                _connectionState.value = ConnectionState.AUTHENTICATED
                reconnectAttempt = 0
                Log.i("WebSocketManager", "WebSocket Connected & Authenticated with Nova Core!")
                
                // 1. Advertise capabilities & initial telemetry
                sendCapabilitiesAndTelemetry(deviceId)

                // 2. Start heartbeat timer
                startHeartbeatTimer(deviceId)
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleIncomingMessage(text)
            }

            override fun onMessage(webSocket: WebSocket, bytes: ByteString) {
                Log.d("WebSocketManager", "Received binary frame: ${bytes.size} bytes")
            }

            override fun onClosing(webSocket: WebSocket, code: Int, reason: String) {
                _connectionState.value = ConnectionState.DISCONNECTED
                stopHeartbeatTimer()
                Log.w("WebSocketManager", "WebSocket closing: $code / $reason")
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                _connectionState.value = ConnectionState.FAILED
                stopHeartbeatTimer()
                Log.e("WebSocketManager", "WebSocket connection failure: ${t.message}")
                scheduleExponentialReconnect()
            }
        })
    }

    private fun sendCapabilitiesAndTelemetry(deviceId: String) {
        try {
            val supportedActions = actionRegistry?.getSupportedActions() ?: listOf(
                "device.get_info", "device.get_telemetry", "wifi.get_info"
            )
            val fullInfo = deviceInfoHandler?.collectDeviceInfo() ?: JSONObject()

            val capEvent = JSONObject().apply {
                put("type", "event")
                put("event", "device.capabilities_advertised")
                put("source", deviceId)
                val payload = JSONObject().apply {
                    put("device_id", deviceId)
                    put("capabilities", supportedActions)
                    put("device_info", fullInfo)
                }
                put("payload", payload)
                put("timestamp", System.currentTimeMillis() / 1000.0)
            }
            sendText(capEvent.toString())
            Log.i("WebSocketManager", "Sent device capability advertisement and full telemetry to Nova Core")
        } catch (e: Exception) {
            Log.e("WebSocketManager", "Failed to send capabilities: ${e.message}")
        }
    }

    private fun startHeartbeatTimer(deviceId: String) {
        stopHeartbeatTimer()
        heartbeatJob = scope.launch {
            while (isActive && _connectionState.value == ConnectionState.AUTHENTICATED) {
                delay(15000)
                sendHeartbeat(deviceId)
            }
        }
    }

    private fun stopHeartbeatTimer() {
        heartbeatJob?.cancel()
        heartbeatJob = null
    }

    private fun sendHeartbeat(deviceId: String) {
        val healthDetails = deviceInfoHandler?.collectDeviceHealth()
        val level = healthDetails?.optInt("battery_percent", 100) ?: 100
        val isCharging = healthDetails?.optBoolean("is_charging", false) ?: false

        val hbJson = JSONObject().apply {
            put("type", "heartbeat")
            put("device_id", deviceId)
            put("battery_level", level)
            put("is_charging", isCharging)
            put("status", "online")
            put("timestamp", System.currentTimeMillis() / 1000.0)
        }
        sendText(hbJson.toString())
    }

    private fun scheduleExponentialReconnect() {
        if (currentServerUrl == null) return

        reconnectJob?.cancel()
        reconnectJob = scope.launch {
            reconnectAttempt++
            val baseDelayMs = 1000.0
            val maxDelayMs = 60000.0
            val delayMs = min(maxDelayMs, baseDelayMs * 2.0.pow(reconnectAttempt.toDouble())).toLong()
            val jitterMs = Random.nextLong(0, 500)
            val totalDelay = delayMs + jitterMs

            Log.i("WebSocketManager", "Scheduling reconnect attempt #$reconnectAttempt in ${totalDelay}ms")
            delay(totalDelay)
            doConnect()
        }
    }

    private fun handleIncomingMessage(text: String) {
        try {
            val json = JSONObject(text)
            val type = json.optString("type")
            if (type == "command" && actionRegistry != null) {
                val cmdId = json.getString("id")
                val action = json.getString("action")
                val payload = json.optJSONObject("payload") ?: JSONObject()

                val result = actionRegistry.dispatch(action, payload)

                val responseJson = JSONObject().apply {
                    put("id", cmdId)
                    put("type", "response")
                    put("status", result.status)
                    put("action", action)
                    put("data", result.data)
                    if (result.error != null) {
                        put("error", result.error)
                    }
                    if (result.errorCode != null) {
                        put("error_code", result.errorCode)
                    }
                    put("timestamp", System.currentTimeMillis() / 1000.0)
                }

                sendText(responseJson.toString())
            }
        } catch (e: Exception) {
            Log.e("WebSocketManager", "Error parsing incoming text: ${e.message}")
        }
    }

    fun sendText(text: String) {
        webSocket?.send(text)
    }

    fun sendBinary(bytes: ByteString) {
        webSocket?.send(bytes)
    }

    fun disconnect() {
        reconnectJob?.cancel()
        stopHeartbeatTimer()
        webSocket?.close(1000, "User Disconnected")
        _connectionState.value = ConnectionState.DISCONNECTED
    }
}
