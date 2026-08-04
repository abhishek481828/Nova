package com.nova.mobile.voice

object VoiceEvents {
    const val EVENT_LISTENING_STARTED = "VoiceListeningStarted"
    const val EVENT_LISTENING_STOPPED = "VoiceListeningStopped"
    const val EVENT_SPEECH_STARTED = "SpeechStarted"
    const val EVENT_SPEECH_ENDED = "SpeechEnded"
    const val EVENT_PARTIAL_RECOGNIZED = "PartialSpeechRecognized"
    const val EVENT_SPEECH_RECOGNIZED = "SpeechRecognized"
    const val EVENT_RECOGNITION_FAILED = "RecognitionFailed"
    const val EVENT_RECOGNITION_CANCELLED = "RecognitionCancelled"
    const val EVENT_RECOGNITION_TIMEOUT = "RecognitionTimeout"
}
