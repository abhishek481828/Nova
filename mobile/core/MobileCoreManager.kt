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
        return mapOf(
            "version" to "3.0.0",
            "is_initialized" to isInitialized,
            "plugins_active" to pluginManager.getActiveCount(),
            "scheduler_running" to scheduler.isRunning,
            "security_ready" to securityManager.isReady,
            "database_ready" to database.isOpen,
            "core_connection" to communicationBridge.connectionState.name,
            "wakeword_listening" to wakeWordManager.isListening,
            "wakeword_detections" to wakeWordManager.metrics.totalDetections
        )
    }
}
