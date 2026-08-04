package com.nova.mobile.voice

data class VoiceMetrics(
    var totalSessions: Int = 0,
    var successfulRecognitions: Int = 0,
    var lastRecognizedText: String = "",
    var lastConfidence: Float = 0.0f,
    var lastSessionDurationMs: Long = 0L,
    var lastRecognitionLanguage: String = "en-US"
) {
    fun recordRecognition(text: String, confidence: Float, durationMs: Long, lang: String = "en-US") {
        totalSessions++
        successfulRecognitions++
        lastRecognizedText = text
        lastConfidence = confidence
        lastSessionDurationMs = durationMs
        lastRecognitionLanguage = lang
    }
}
