package com.nova.mobile.voice

import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log

interface SpeechRecognitionCallback {
    fun onSpeechStarted()
    fun onPartialResults(text: String)
    fun onFinalResults(text: String, confidence: Float)
    fun onError(errorCode: Int, message: String)
}

class SpeechRecognizerManager(private val context: Context) : RecognitionListener {
    companion object {
        private const val TAG = "SpeechRecognizerManager"
    }

    private var speechRecognizer: SpeechRecognizer? = null
    private var callback: SpeechRecognitionCallback? = null
    var isListening: Boolean = false
        private set

    fun initialize(cb: SpeechRecognitionCallback): Boolean {
        this.callback = cb
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            Log.e(TAG, "SpeechRecognizer service is unavailable on this Android device.")
            return false
        }
        return try {
            speechRecognizer = SpeechRecognizer.createSpeechRecognizer(context)
            speechRecognizer?.setRecognitionListener(this)
            Log.i(TAG, "SpeechRecognizer initialized successfully.")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to create SpeechRecognizer", e)
            false
        }
    }

    fun startListening(language: String = "en-US", partialResults: Boolean = true) {
        if (isListening) return
        val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
            putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            putExtra(RecognizerIntent.EXTRA_LANGUAGE, language)
            putExtra(RecognizerIntent.EXTRA_PARTIAL_RESULTS, partialResults)
            putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
        }
        try {
            speechRecognizer?.startListening(intent)
            isListening = true
            Log.i(TAG, "Started speech recognition (lang=$language).")
        } catch (e: Exception) {
            Log.e(TAG, "Error starting SpeechRecognizer", e)
            callback?.onError(-1, e.message ?: "Failed to start listening")
        }
    }

    fun stopListening() {
        if (!isListening) return
        try {
            speechRecognizer?.stopListening()
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping SpeechRecognizer", e)
        } finally {
            isListening = false
        }
    }

    fun destroy() {
        stopListening()
        speechRecognizer?.destroy()
        speechRecognizer = null
        callback = null
    }

    // RecognitionListener Callbacks
    override fun onReadyForSpeech(params: Bundle?) { Log.d(TAG, "onReadyForSpeech") }
    override fun onBeginningOfSpeech() { callback?.onSpeechStarted() }
    override fun onRmsChanged(rmsdB: Float) {}
    override fun onBufferReceived(buffer: ByteArray?) {}
    override fun onEndOfSpeech() { isListening = false }
    override fun onError(error: Int) {
        isListening = false
        callback?.onError(error, "Speech recognition error code: $error")
    }

    override fun onResults(results: Bundle?) {
        isListening = false
        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
        val scores = results?.getFloatArray(SpeechRecognizer.CONFIDENCE_SCORES)

        val text = matches?.firstOrNull() ?: ""
        val confidence = scores?.firstOrNull() ?: 0.95f

        callback?.onFinalResults(text, confidence)
    }

    override fun onPartialResults(partialResults: Bundle?) {
        val matches = partialResults?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
        val text = matches?.firstOrNull() ?: ""
        if (text.isNotBlank()) {
            callback?.onPartialResults(text)
        }
    }

    override fun onEvent(eventType: Int, params: Bundle?) {}
}
