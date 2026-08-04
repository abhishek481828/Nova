package com.nova.mobile.voice

import android.content.Context
import android.util.Log
import com.nova.mobile.lifecycle.LifecycleManager

typealias SpeechResultListener = (text: String, confidence: Float) -> Unit

class VoiceManager(
    private val context: Context,
    private val lifecycleManager: LifecycleManager,
    val config: VoiceConfiguration = VoiceConfiguration()
) : SpeechRecognitionCallback {

    companion object {
        private const val TAG = "VoiceManager"
    }

    val speechRecognizerManager: SpeechRecognizerManager by lazy { SpeechRecognizerManager(context) }
    val metrics: VoiceMetrics = VoiceMetrics()
    var currentSession: VoiceSession? = null
        private set

    private val resultListeners = mutableListOf<SpeechResultListener>()

    fun startVoiceSession(): VoiceSession {
        currentSession?.let {
            if (it.currentState != VoiceState.IDLE && it.currentState != VoiceState.COMPLETED && it.currentState != VoiceState.CANCELLED && it.currentState != VoiceState.ERROR) {
                Log.w(TAG, "Cancelling existing voice session [${it.sessionId}]")
                cancelVoiceSession()
            }
        }

        val session = VoiceSession()
        currentSession = session
        session.transitionTo(VoiceState.LISTENING)

        lifecycleManager.publishEvent(VoiceEvents.EVENT_LISTENING_STARTED, mapOf("sessionId" to session.sessionId, "lang" to config.language))

        // Initialize SpeechRecognizer
        if (!speechRecognizerManager.isListening) {
            speechRecognizerManager.initialize(this)
            speechRecognizerManager.startListening(config.language, config.partialResultsEnabled)
        }

        session.transitionTo(VoiceState.RECORDING)
        Log.i(TAG, "Started Voice Session [${session.sessionId}] (language=${config.language})")
        return session
    }

    fun stopVoiceSession() {
        val session = currentSession ?: return
        if (session.currentState == VoiceState.RECORDING || session.currentState == VoiceState.LISTENING) {
            session.transitionTo(VoiceState.RECOGNIZING)
            speechRecognizerManager.stopListening()
            lifecycleManager.publishEvent(VoiceEvents.EVENT_LISTENING_STOPPED, mapOf("sessionId" to session.sessionId))
        }
    }

    fun cancelVoiceSession() {
        val session = currentSession ?: return
        speechRecognizerManager.stopListening()
        session.transitionTo(VoiceState.CANCELLED)
        lifecycleManager.publishEvent(VoiceEvents.EVENT_RECOGNITION_CANCELLED, mapOf("sessionId" to session.sessionId))
        Log.i(TAG, "Cancelled Voice Session [${session.sessionId}]")
    }

    fun simulateRecognizedText(text: String, confidence: Float = 0.95f) {
        val session = currentSession ?: startVoiceSession()
        onFinalResults(text, confidence)
    }

    // SpeechRecognitionCallback Implementation
    override fun onSpeechStarted() {
        currentSession?.transitionTo(VoiceState.RECORDING)
        lifecycleManager.publishEvent(VoiceEvents.EVENT_SPEECH_STARTED, mapOf("sessionId" to (currentSession?.sessionId ?: "")))
    }

    override fun onPartialResults(text: String) {
        lifecycleManager.publishEvent(VoiceEvents.EVENT_PARTIAL_RECOGNIZED, mapOf("text" to text))
    }

    override fun onFinalResults(text: String, confidence: Float) {
        val session = currentSession
        val durationMs = session?.getDurationMs() ?: 0L

        metrics.recordRecognition(text, confidence, durationMs, config.language)
        session?.transitionTo(VoiceState.COMPLETED)

        lifecycleManager.publishEvent(VoiceEvents.EVENT_SPEECH_ENDED, mapOf("sessionId" to (session?.sessionId ?: "")))
        lifecycleManager.publishEvent(
            VoiceEvents.EVENT_SPEECH_RECOGNIZED,
            mapOf(
                "text" to text,
                "confidence" to confidence,
                "duration_ms" to durationMs,
                "language" to config.language
            )
        )

        Log.i(TAG, "🎯 SPEECH RECOGNIZED: \"$text\" (Confidence: $confidence, Duration: ${durationMs}ms)")

        for (listener in resultListeners) {
            try {
                listener(text, confidence)
            } catch (e: Exception) {
                Log.e(TAG, "Error notifying speech result listener", e)
            }
        }
    }

    override fun onError(errorCode: Int, message: String) {
        val session = currentSession
        session?.transitionTo(VoiceState.ERROR)
        lifecycleManager.publishEvent(VoiceEvents.EVENT_RECOGNITION_FAILED, mapOf("error" to message, "code" to errorCode))
        Log.e(TAG, "Speech Recognition Failed: $message (code=$errorCode)")
    }

    fun addResultListener(listener: SpeechResultListener) {
        resultListeners.add(listener)
    }

    fun removeResultListener(listener: SpeechResultListener) {
        resultListeners.remove(listener)
    }
}
