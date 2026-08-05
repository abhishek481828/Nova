package com.nova.companion.voice

import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.media.ToneGenerator
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.util.Log
import java.util.Locale
import java.util.concurrent.atomic.AtomicBoolean

class OfflineWakeWordDetector(
    private val context: Context,
    private val onWakeWordDetected: (String) -> Unit
) {
    private val isRunning = AtomicBoolean(false)
    private val mainHandler = Handler(Looper.getMainLooper())
    private var activeRecognizer: SpeechRecognizer? = null

    fun start() {
        if (isRunning.getAndSet(true)) return
        Log.i("OfflineWakeWordDetector", "Offline Low-Power Wake Word Engine Started: Listening for 'Hey Nova'...")
        listenLoop()
    }

    private fun listenLoop() {
        if (!isRunning.get()) return

        mainHandler.post {
            try {
                if (!SpeechRecognizer.isRecognitionAvailable(context)) {
                    Log.w("OfflineWakeWordDetector", "SpeechRecognition unavailable")
                    return@post
                }

                activeRecognizer?.destroy()
                val recognizer = SpeechRecognizer.createSpeechRecognizer(context)
                activeRecognizer = recognizer

                val intent = Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.getDefault())
                    putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                }

                recognizer.setRecognitionListener(object : RecognitionListener {
                    override fun onReadyForSpeech(params: Bundle?) {}
                    override fun onBeginningOfSpeech() {}
                    override fun onRmsChanged(rmsdB: Float) {}
                    override fun onBufferReceived(buffer: ByteArray?) {}
                    override fun onEndOfSpeech() {}
                    override fun onError(error: Int) {
                        try { recognizer.destroy() } catch (e: Exception) {}
                        if (isRunning.get()) {
                            mainHandler.postDelayed({ listenLoop() }, 400)
                        }
                    }

                    override fun onResults(results: Bundle?) {
                        val matches = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        val text = matches?.firstOrNull() ?: ""
                        val lower = text.lowercase()

                        if (lower.contains("nova") || lower.contains("hey nova") || lower.contains("ok nova")) {
                            Log.i("OfflineWakeWordDetector", "🎯 WAKE WORD DETECTED: '$text'")
                            playWakeChime()
                            onWakeWordDetected(text)
                        }
                        try { recognizer.destroy() } catch (e: Exception) {}
                        if (isRunning.get()) {
                            mainHandler.postDelayed({ listenLoop() }, 400)
                        }
                    }

                    override fun onPartialResults(partialResults: Bundle?) {}
                    override fun onEvent(eventType: Int, params: Bundle?) {}
                })

                recognizer.startListening(intent)
            } catch (e: Exception) {
                Log.e("OfflineWakeWordDetector", "Error in main loop speech recognizer", e)
                if (isRunning.get()) {
                    mainHandler.postDelayed({ listenLoop() }, 1000)
                }
            }
        }
    }

    fun stop() {
        isRunning.set(false)
        mainHandler.post {
            try { activeRecognizer?.destroy() } catch (e: Exception) {}
            activeRecognizer = null
        }
    }

    private fun playWakeChime() {
        try {
            val tone = ToneGenerator(AudioManager.STREAM_NOTIFICATION, 100)
            tone.startTone(ToneGenerator.TONE_PROP_BEEP, 150)
        } catch (e: Exception) {
            Log.e("OfflineWakeWordDetector", "Failed to play chime", e)
        }
    }
}
