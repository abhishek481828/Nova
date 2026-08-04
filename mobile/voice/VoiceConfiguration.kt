package com.nova.mobile.voice

/**
 * Configuration options for Voice Pipeline & Speech Recognition.
 */
data class VoiceConfiguration(
    val language: String = "en-US",
    val silenceTimeoutMs: Long = 3000L,
    val maxRecordingDurationMs: Long = 10000L,
    val minSpeechDurationMs: Long = 500L,
    val wakeSoundEnabled: Boolean = true,
    val partialResultsEnabled: Boolean = true,
    val microphoneSensitivity: Float = 1.0f
)
