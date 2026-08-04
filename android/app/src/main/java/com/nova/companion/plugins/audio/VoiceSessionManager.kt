package com.nova.companion.plugins.audio

import android.content.Context
import android.util.Log
import com.nova.companion.event.EventBus
import org.json.JSONObject
import java.util.UUID
import java.util.concurrent.atomic.AtomicBoolean

class VoiceSessionManager(private val context: Context, private val streamManager: AudioStreamManager) {

    companion object {
        private const val TAG = "VoiceSessionManager"
    }

    private val isSessionActive = AtomicBoolean(false)
    private var currentSessionId: String = ""
    private var sessionStartTime = 0L

    fun startSession(): JSONObject {
        if (isSessionActive.get()) {
            return JSONObject().apply {
                put("status", "already_active")
                put("session_id", currentSessionId)
            }
        }

        currentSessionId = "VOICE_SESS_" + UUID.randomUUID().toString().take(8)
        sessionStartTime = System.currentTimeMillis()
        isSessionActive.set(true)

        streamManager.startCapture()

        val data = JSONObject().apply {
            put("status", "session_started")
            put("session_id", currentSessionId)
            put("start_time", sessionStartTime)
        }

        EventBus.publish("Voice Session Started", data)
        Log.i(TAG, "Voice session started: $currentSessionId")
        return data
    }

    fun stopSession(): JSONObject {
        if (!isSessionActive.get()) {
            return JSONObject().apply {
                put("status", "no_active_session")
            }
        }

        isSessionActive.set(false)
        streamManager.stopCapture()

        val durationSec = (System.currentTimeMillis() - sessionStartTime) / 1000.0
        val telemetry = streamManager.getTelemetry()

        val data = JSONObject().apply {
            put("status", "session_ended")
            put("session_id", currentSessionId)
            put("duration_seconds", durationSec)
            put("packets_transmitted", telemetry.optLong("packets_sent", 0L))
            put("bytes_transmitted", telemetry.optLong("total_bytes", 0L))
            put("connection_quality", "EXCELLENT")
        }

        EventBus.publish("Voice Session Ended", data)
        Log.i(TAG, "Voice session ended: $currentSessionId (Duration: ${durationSec}s)")
        return data
    }

    fun isSessionActive(): Boolean = isSessionActive.get()
    fun getSessionId(): String = currentSessionId
}
