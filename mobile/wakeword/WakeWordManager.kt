package com.nova.mobile.wakeword

import android.content.Context
import android.util.Log
import com.nova.mobile.lifecycle.LifecycleManager

typealias WakeWordDetectionListener = (phrase: String, score: Float) -> Unit

class WakeWordManager(
    private val context: Context,
    private val lifecycleManager: LifecycleManager,
    val config: WakeWordConfiguration = WakeWordConfiguration()
) {
    companion object {
        private const val TAG = "WakeWordManager"
    }

    val micManager: MicrophoneManager by lazy { MicrophoneManager(context) }
    val engine: WakeWordEngine by lazy { WakeWordEngine(config) }
    val metrics: WakeWordMetrics = WakeWordMetrics()

    var isListening: Boolean = false
        private set

    private val detectionListeners = mutableListOf<WakeWordDetectionListener>()

    fun startListening(): Boolean {
        if (isListening) {
            Log.w(TAG, "WakeWordManager is already listening.")
            return true
        }

        if (!micManager.hasRecordPermission()) {
            Log.e(TAG, "Cannot start listening: Microphone permission missing!")
            lifecycleManager.publishEvent(WakeWordEvents.EVENT_PERMISSION_MISSING, emptyMap())
            return false
        }

        if (!engine.start()) {
            Log.e(TAG, "Failed to start WakeWordEngine.")
            lifecycleManager.publishEvent(WakeWordEvents.EVENT_DETECTION_FAILED, mapOf("reason" to "Engine initialization failed"))
            return false
        }

        if (!micManager.startCapturing(config.audioSampleRate, config.frameSizeSamples)) {
            Log.e(TAG, "Failed to start microphone capture.")
            engine.stop()
            lifecycleManager.publishEvent(WakeWordEvents.EVENT_DETECTION_FAILED, mapOf("reason" to "Microphone capture failed"))
            return false
        }

        isListening = true
        lifecycleManager.publishEvent(WakeWordEvents.EVENT_LISTENING_STARTED, mapOf("phrase" to config.wakePhrase))
        Log.i(TAG, "WakeWordManager started listening for '${config.wakePhrase}'")
        return true
    }

    fun processNextAudioFrame(): Boolean {
        if (!isListening) return false

        val buffer = ShortArray(config.frameSizeSamples)
        val readCount = micManager.readChunk(buffer)

        if (readCount <= 0) return false

        val score = engine.processAudioFrame(buffer, readCount)
        if (score >= config.detectionThreshold) {
            triggerWakeDetection(score)
            return true
        }
        return false
    }

    fun triggerWakeDetection(score: Float = 0.95f) {
        metrics.recordDetection()
        Log.i(TAG, "🎯 WAKE WORD DETECTED: '${config.wakePhrase}' (Score: $score, Total Count: ${metrics.totalDetections})")

        lifecycleManager.publishEvent(
            WakeWordEvents.EVENT_DETECTED,
            mapOf(
                "phrase" to config.wakePhrase,
                "confidence" to score,
                "timestamp" to metrics.lastDetectionTimestamp,
                "count" to metrics.totalDetections
            )
        )

        for (listener in detectionListeners) {
            try {
                listener(config.wakePhrase, score)
            } catch (e: Exception) {
                Log.e(TAG, "Error notifying wake detection listener", e)
            }
        }
    }

    fun stopListening() {
        if (!isListening) return
        micManager.stopCapturing()
        engine.stop()
        isListening = false
        lifecycleManager.publishEvent(WakeWordEvents.EVENT_LISTENING_STOPPED, emptyMap())
        Log.i(TAG, "WakeWordManager stopped listening.")
    }

    fun restartEngine(): Boolean {
        Log.i(TAG, "Restarting WakeWordEngine...")
        stopListening()
        metrics.recordRecovery()
        val success = startListening()
        if (success) {
            lifecycleManager.publishEvent(WakeWordEvents.EVENT_ENGINE_RESTARTED, mapOf("attempt" to metrics.totalRecoveryAttempts))
        }
        return success
    }

    fun addDetectionListener(listener: WakeWordDetectionListener) {
        detectionListeners.add(listener)
    }

    fun removeDetectionListener(listener: WakeWordDetectionListener) {
        detectionListeners.remove(listener)
    }
}
