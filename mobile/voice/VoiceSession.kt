package com.nova.mobile.voice

import android.util.Log

enum class VoiceState {
    IDLE,
    LISTENING,
    RECORDING,
    RECOGNIZING,
    COMPLETED,
    CANCELLED,
    ERROR
}

class VoiceSession(val sessionId: String = java.util.UUID.randomUUID().toString()) {
    companion object {
        private const val TAG = "VoiceSession"
    }

    var currentState: VoiceState = VoiceState.IDLE
        private set

    val startTimestamp: Long = System.currentTimeMillis()
    var endTimestamp: Long = 0L
        private set

    fun transitionTo(newState: VoiceState): Boolean {
        Log.i(TAG, "Session [$sessionId] State Transition: $currentState -> $newState")
        currentState = newState
        if (newState == VoiceState.COMPLETED || newState == VoiceState.CANCELLED || newState == VoiceState.ERROR) {
            endTimestamp = System.currentTimeMillis()
        }
        return true
    }

    fun getDurationMs(): Long {
        return if (endTimestamp > 0) (endTimestamp - startTimestamp) else (System.currentTimeMillis() - startTimestamp)
    }
}
