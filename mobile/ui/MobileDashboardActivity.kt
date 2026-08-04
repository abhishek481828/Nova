package com.nova.mobile.ui

import android.app.Activity
import android.os.Bundle
import android.widget.TextView
import com.nova.mobile.core.MobileCoreManager

/**
 * Nova v3.0 Mobile Foundation Status Dashboard UI
 */
class MobileDashboardActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val core = MobileCoreManager.getInstance(this)
        if (!core.isInitialized) {
            core.initialize()
        }

        val health = core.getHealthStatus()

        val tv = TextView(this).apply {
            textSize = 15f
            setPadding(32, 32, 32, 32)
            text = """
                === NOVA MOBILE v3.0 DASHBOARD ===
                
                • Nova Status         : ${if (core.isInitialized) "ACTIVE" else "OFFLINE"}
                • Running Services    : ${if (core.scheduler.isRunning) "Foreground & Task Scheduler Active" else "Stopped"}
                • Plugin Status       : ${health["plugins_active"]} active plugins
                • Battery State       : Optimal (Low Impact)
                • Connectivity        : Standby
                • Nova Core Status    : ${health["core_connection"]}
                • Security KeyStore   : ${if (health["security_ready"] == true) "READY" else "INITIALIZING"}
                • Database            : ${if (health["database_ready"] == true) "ENCRYPTED & OPEN" else "CLOSED"}
                
                === WAKE WORD ENGINE (OFFLINE) ===
                • Phrase Configured   : "${core.wakeWordManager.config.wakePhrase}"
                • Engine Status       : ${if (core.wakeWordManager.isListening) "LISTENING 🟢" else "IDLE ⚪"}
                • Microphone Status   : ${if (core.wakeWordManager.micManager.isRecording) "CAPTURING 🎙️" else "OFF 🔇"}
                • Sensitivity         : ${core.wakeWordManager.config.sensitivity} (Threshold: ${core.wakeWordManager.config.detectionThreshold})
                • Detection Counter   : ${core.wakeWordManager.metrics.totalDetections} detections
                • Last Detection      : ${if (core.wakeWordManager.metrics.lastDetectionTimestamp > 0) core.wakeWordManager.metrics.lastDetectionTimestamp else "None"}
                
                === VOICE PIPELINE & SPEECH RECOGNITION ===
                • Session State       : ${health["voice_state"]}
                • Language            : ${core.voiceManager.config.language}
                • Recognized Text     : "${core.voiceManager.metrics.lastRecognizedText}"
                • Confidence Score    : ${core.voiceManager.metrics.lastConfidence}
                • Session Duration    : ${core.voiceManager.metrics.lastSessionDurationMs}ms
                • Total Sessions      : ${core.voiceManager.metrics.totalSessions} sessions
                • Version             : 3.0.0 (Phase 3 Voice Pipeline Active)
            """.trimIndent()
        }

        setContentView(tv)
    }
}
