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
                
                === LOCAL COMMAND ENGINE ===
                • Detected Intent     : ${health["last_intent"]}
                • Executing Plugin    : ${core.commandEngine.history.getLastResult()?.pluginUsed ?: "None"}
                • Extracted Entities  : ${core.commandEngine.history.getLastResult()?.entities ?: "{}"}
                • Spoken Response     : "${health["last_spoken_response"]}"
                • Execution Result    : ${if (core.commandEngine.history.getLastResult()?.isSuccess == true) "SUCCESS 🟢" else "READY ⚪"}
                • Execution Time      : ${core.commandEngine.history.getLastResult()?.executionTimeMs ?: 0}ms
                • Total Commands      : ${health["total_commands_executed"]} executed
                
                === HYBRID AI ROUTER (PHASE 5) ===
                • Routing Policy      : ${health["routing_policy"]}
                • Nova Core Status    : ${if (health["nova_core_online"] == true) "ONLINE 🟢" else "OFFLINE 🔴"}
                • Core Latency        : ${health["nova_core_latency_ms"]}ms
                • Last Exec Target    : ${core.hybridRouter.routingEngine.policy.name}
                
                === PERSONAL MEMORY (PHASE 6) ===
                • Total Memories      : ${health["memory_total_entries"]}
                • Favorite Contacts   : ${health["memory_favorite_contacts"]}
                • Favorite Apps       : ${health["memory_favorite_apps"]}
                • Recent Commands     : ${health["memory_recent_commands"]}
                • Sync with Core      : ${if (core.memoryManager.config.syncWithNovaCore) "ENABLED 🔄" else "DISABLED ⚪"}
                
                === SMART AUTOMATION (PHASE 7) ===
                • Total Routines      : ${health["automation_total_routines"]}
                • Active Routines     : ${health["automation_enabled_routines"]}
                • Total Executions    : ${health["automation_total_executions"]}
                • Failed Executions   : ${health["automation_failed_executions"]}
                • Scheduler Running   : ${if (health["automation_scheduler_running"] == true) "YES 🟢" else "NO 🔴"}
                • All Paused          : ${if (core.automationManager.routineManager.allPaused) "YES ⏸" else "NO ▶"}
                • Version             : 3.0.0 (Phase 7 Smart Automation Active)
            """.trimIndent()
        }

        setContentView(tv)
    }
}
