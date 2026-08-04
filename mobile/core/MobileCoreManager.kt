package com.nova.mobile.core

import android.content.Context
import android.util.Log
import com.nova.mobile.plugins.PluginManager
import com.nova.mobile.services.NovaMobileForegroundService
import com.nova.mobile.settings.ConfigurationManager
import com.nova.mobile.storage.MobileDatabase
import com.nova.mobile.security.MobileSecurityManager
import com.nova.mobile.lifecycle.LifecycleManager
import com.nova.mobile.scheduler.TaskScheduler
import com.nova.mobile.communication.CommunicationBridge

/**
 * Nova v3.0 — Mobile Core Manager
 * Orchestrates application startup, dependency initialization, plugin loading,
 * service registration, configuration loading, health monitoring, and graceful shutdown.
 */
class MobileCoreManager private constructor(private val context: Context) {

    companion object {
        private const val TAG = "MobileCoreManager"

        @Volatile
        private var INSTANCE: MobileCoreManager? = null

        fun getInstance(context: Context): MobileCoreManager {
            return INSTANCE ?: synchronized(this) {
                INSTANCE ?: MobileCoreManager(context.applicationContext).also { INSTANCE = it }
            }
        }
    }

    var isInitialized: Boolean = false
        private set

    val configurationManager: ConfigurationManager by lazy { ConfigurationManager(context) }
    val database: MobileDatabase by lazy { MobileDatabase(context) }
    val securityManager: MobileSecurityManager by lazy { MobileSecurityManager(context) }
    val pluginManager: PluginManager by lazy { PluginManager(context) }
    val lifecycleManager: LifecycleManager by lazy { LifecycleManager(context) }
    val scheduler: TaskScheduler by lazy { TaskScheduler(context) }
    val communicationBridge: CommunicationBridge by lazy { CommunicationBridge(context) }
    val wakeWordManager: com.nova.mobile.wakeword.WakeWordManager by lazy { com.nova.mobile.wakeword.WakeWordManager(context, lifecycleManager) }
    val voiceManager: com.nova.mobile.voice.VoiceManager by lazy { com.nova.mobile.voice.VoiceManager(context, lifecycleManager) }
    val commandEngine: com.nova.mobile.command.CommandEngine by lazy { com.nova.mobile.command.CommandEngine(context, lifecycleManager) }
    val hybridRouter: com.nova.mobile.hybrid.HybridRouter by lazy { com.nova.mobile.hybrid.HybridRouter(context, lifecycleManager, commandEngine) }
    val memoryManager: com.nova.mobile.memory.MemoryManager by lazy { com.nova.mobile.memory.MemoryManager(context, lifecycleManager) }
    val automationManager: com.nova.mobile.automation.AutomationManager by lazy { com.nova.mobile.automation.AutomationManager(context, lifecycleManager, commandEngine) }

    fun initialize(): Boolean {
        if (isInitialized) {
            Log.w(TAG, "Mobile Core is already initialized.")
            return true
        }

        return try {
            Log.i(TAG, "Starting Nova Mobile Core v3.0 initialization...")

            // 1. Load Configurations
            configurationManager.initialize()

            // 2. Initialize Encrypted Storage & KeyStore Security
            securityManager.initialize()
            database.initialize()

            // 3. Initialize Lifecycle Monitoring
            lifecycleManager.initialize()

            // 4. Initialize Scheduler
            scheduler.initialize()

            // 5. Initialize Communication Abstraction
            communicationBridge.initialize()

            // 6. Register & Load Plugins
            pluginManager.initialize()

            // 7. Auto-connect Wake Word Detection -> Voice Session Pipeline
            wakeWordManager.addDetectionListener { phrase, _ ->
                Log.i(TAG, "Wake Word '$phrase' detected -> Automatically starting Voice Recording Session!")
                voiceManager.startVoiceSession()
            }

            // 8. Auto-connect Voice Recognition -> Hybrid AI Router (Phase 5)
            voiceManager.addResultListener { recognizedText, _ ->
                Log.i(TAG, "Speech Recognized: \"$recognizedText\" -> Forwarding to Hybrid AI Router!")
                val hybridResult = hybridRouter.route(recognizedText)

                // 8a. Memory query interception (Phase 6) — check before normal routing
                val memoryResponse = memoryManager.handleMemoryQuery(recognizedText)
                if (memoryResponse != null) {
                    Log.i(TAG, "Memory Query handled: $memoryResponse")
                    lifecycleManager.publishEvent("MemoryQueryAnswered", mapOf("response" to memoryResponse))
                }
            }

            // 9. Connect Hybrid Router results -> Memory Learning (Phase 6)
            hybridRouter.addResultListener { result ->
                if (result.isSuccess && result.target == com.nova.mobile.hybrid.ExecutionTarget.LOCAL_ANDROID) {
                    val last = commandEngine.history.getLastResult()
                    if (last != null) {
                        memoryManager.onCommandExecuted(
                            last.intent.name,
                            last.entities.mapValues { it.value.toString() },
                            result.intent
                        )
                    }
                }
            }

            // 10. Start Nova Core discovery probing
            hybridRouter.deviceDiscovery.startProbing()
            hybridRouter.deviceDiscovery.addStateListener { online ->
                lifecycleManager.publishEvent("NovaCoreStateChanged", mapOf("online" to online))
                Log.i(TAG, "Nova Core is now ${if (online) "ONLINE" else "OFFLINE"}")
                automationManager.triggerManager.onNovaCoreConnected().also { if (!online) automationManager.triggerManager.onNovaCoreDisconnected() }
            }

            // 11. Start Automation Manager & Scheduler (Phase 7)
            automationManager.start()

            isInitialized = true
            lifecycleManager.publishEvent("AppStarted", mapOf("version" to "3.0.0"))
            Log.i(TAG, "Nova Mobile Core v3.0 initialized successfully.")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to initialize Nova Mobile Core", e)
            false
        }
    }

    fun shutdown() {
        if (!isInitialized) return
        Log.i(TAG, "Shutting down Nova Mobile Core v3.0...")
        try {
            lifecycleManager.publishEvent("AppStopped", emptyMap())
            automationManager.stop()
            hybridRouter.deviceDiscovery.stopProbing()
            voiceManager.cancelVoiceSession()
            wakeWordManager.stopListening()
            pluginManager.shutdownAll()
            scheduler.cancelAll()
            communicationBridge.shutdown()
            database.close()
            isInitialized = false
            Log.i(TAG, "Nova Mobile Core v3.0 shutdown complete.")
        } catch (e: Exception) {
            Log.e(TAG, "Error during Mobile Core shutdown", e)
        }
    }

    fun getHealthStatus(): Map<String, Any> {
        val lastResult = commandEngine.history.getLastResult()
        val discovery = hybridRouter.deviceDiscovery
        return mapOf(
            "version" to "3.0.0",
            "is_initialized" to isInitialized,
            "plugins_active" to pluginManager.getActiveCount(),
            "scheduler_running" to scheduler.isRunning,
            "security_ready" to securityManager.isReady,
            "database_ready" to database.isOpen,
            "core_connection" to communicationBridge.connectionState.name,
            "wakeword_listening" to wakeWordManager.isListening,
            "wakeword_detections" to wakeWordManager.metrics.totalDetections,
            "voice_state" to (voiceManager.currentSession?.currentState?.name ?: "IDLE"),
            "last_recognized_text" to voiceManager.metrics.lastRecognizedText,
            "recognition_confidence" to voiceManager.metrics.lastConfidence,
            "last_intent" to (lastResult?.intent?.name ?: "NONE"),
            "last_spoken_response" to (lastResult?.spokenResponse ?: "None"),
            "total_commands_executed" to commandEngine.history.getTotalCount(),
            "nova_core_online" to discovery.isNovaCoreOnline,
            "nova_core_latency_ms" to discovery.lastLatencyMs,
            "routing_policy" to hybridRouter.routingEngine.policy.name,
            "memory_total_entries" to memoryManager.store.totalCount(),
            "memory_favorite_contacts" to memoryManager.repository.list(com.nova.mobile.memory.MemoryCategory.FAVORITE_CONTACT).size,
            "memory_favorite_apps" to memoryManager.repository.list(com.nova.mobile.memory.MemoryCategory.FAVORITE_APP).size,
            "memory_recent_commands" to memoryManager.repository.list(com.nova.mobile.memory.MemoryCategory.RECENT_COMMAND).size,
            "automation_total_routines" to automationManager.repository.count(),
            "automation_enabled_routines" to automationManager.repository.countEnabled(),
            "automation_total_executions" to automationManager.history.totalCount(),
            "automation_failed_executions" to automationManager.history.failureCount(),
            "automation_scheduler_running" to automationManager.scheduler.isRunning
        )
    }
}
