package com.nova.mobile.wakeword

/**
 * Configuration options for the offline Wake Word Engine.
 */
data class WakeWordConfiguration(
    val wakePhrase: String = "Hey Nova",
    val sensitivity: Float = 0.75f,
    val detectionThreshold: Float = 0.80f,
    val wakeSoundEnabled: Boolean = true,
    val adaptiveSleepEnabled: Boolean = true,
    val audioSampleRate: Int = 16000,
    val frameSizeSamples: Int = 512,
    val maxRecoveryAttempts: Int = 5
)
