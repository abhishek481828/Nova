package com.nova.mobile.wakeword

import android.util.Log

class WakeWordEngine(private val config: WakeWordConfiguration) {
    companion object {
        private const val TAG = "WakeWordEngine"
    }

    var isEngineActive: Boolean = false
        private set

    fun start(): Boolean {
        isEngineActive = true
        Log.i(TAG, "Offline WakeWordEngine started (Phrase: '${config.wakePhrase}', Sensitivity: ${config.sensitivity}).")
        return true
    }

    fun processAudioFrame(buffer: ShortArray, readCount: Int): Float {
        if (!isEngineActive || readCount <= 0) return 0.0f

        // Compute Root Mean Square (RMS) audio energy level
        var sumSquares = 0.0
        for (i in 0 until readCount) {
            val sample = buffer[i].toDouble()
            sumSquares += sample * sample
        }
        val rms = Math.sqrt(sumSquares / readCount)

        // Normalize RMS against sensitivity & threshold
        val normalizedEnergy = (rms / 32768.0).toFloat() * (1.0f + config.sensitivity)

        // Return calculated confidence score
        return if (normalizedEnergy > config.detectionThreshold) {
            Math.min(1.0f, normalizedEnergy)
        } else {
            normalizedEnergy * 0.5f
        }
    }

    fun stop() {
        isEngineActive = false
        Log.i(TAG, "Offline WakeWordEngine stopped.")
    }
}
