package com.nova.mobile.plugins

import android.content.Context
import android.util.Log

interface MobilePlugin {
    val id: String
    val name: String
    val version: String
    val minCoreVersion: String
    val dependencies: List<String>
    var isEnabled: Boolean

    fun onInitialize(context: Context): Boolean
    fun onEnable()
    fun onDisable()
    fun onShutdown()
}

abstract class BaseMobilePlugin(
    override val id: String,
    override val name: String,
    override val version: String = "1.0.0",
    override val minCoreVersion: String = "3.0.0",
    override val dependencies: List<String> = emptyList()
) : MobilePlugin {
    override var isEnabled: Boolean = false

    override fun onInitialize(context: Context): Boolean = true
    override fun onEnable() { isEnabled = true }
    override fun onDisable() { isEnabled = false }
    override fun onShutdown() { isEnabled = false }
}

class PluginManager(private val context: Context) {
    companion object {
        private const val TAG = "PluginManager"
    }

    private val plugins = mutableMapOf<String, MobilePlugin>()

    fun initialize() {
        Log.i(TAG, "Initializing PluginManager...")
    }

    fun registerPlugin(plugin: MobilePlugin): Boolean {
        if (plugins.containsKey(plugin.id)) {
            Log.w(TAG, "Plugin already registered: ${plugin.id}")
            return false
        }

        // Validate dependencies
        for (dep in plugin.dependencies) {
            if (!plugins.containsKey(dep)) {
                Log.e(TAG, "Plugin ${plugin.id} missing required dependency: $dep")
                return false
            }
        }

        if (plugin.onInitialize(context)) {
            plugins[plugin.id] = plugin
            plugin.onEnable()
            Log.i(TAG, "Successfully registered and enabled plugin: ${plugin.name} (id=${plugin.id})")
            return true
        }
        return false
    }

    fun unregisterPlugin(pluginId: String): Boolean {
        val plugin = plugins[pluginId] ?: return false
        plugin.onDisable()
        plugin.onShutdown()
        plugins.remove(pluginId)
        Log.i(TAG, "Unregistered plugin: $pluginId")
        return true
    }

    fun getPlugin(pluginId: String): MobilePlugin? = plugins[pluginId]

    fun getAllPlugins(): List<MobilePlugin> = plugins.values.toList()

    fun getActiveCount(): Int = plugins.values.count { it.isEnabled }

    fun shutdownAll() {
        for (plugin in plugins.values) {
            try {
                plugin.onDisable()
                plugin.onShutdown()
            } catch (e: Exception) {
                Log.e(TAG, "Error shutting down plugin: ${plugin.id}", e)
            }
        }
        plugins.clear()
    }
}
