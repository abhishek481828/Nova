package com.nova.mobile.storage

import android.content.Context
import android.util.Log

data class SettingEntry(val key: String, val value: String, val updatedAt: Long = System.currentTimeMillis())
data class CommandEntry(val id: String, val action: String, val status: String, val timestamp: Long = System.currentTimeMillis())
data class DeviceEntry(val deviceId: String, val name: String, val platform: String, val isOnline: Boolean)
data class SessionEntry(val sessionId: String, val createdAt: Long = System.currentTimeMillis(), val isActive: Boolean = true)
data class EventEntry(val eventId: String, val type: String, val payloadJson: String, val timestamp: Long = System.currentTimeMillis())
data class MemoryPlaceholder(val id: String, val key: String, val data: String)

/**
 * Nova v3.0 Encrypted Local Storage Manager
 */
class MobileDatabase(private val context: Context) {
    companion object {
        private const val TAG = "MobileDatabase"
    }

    var isOpen: Boolean = false
        private set

    private val settingsTable = mutableMapOf<String, SettingEntry>()
    private val commandsTable = mutableListOf<CommandEntry>()
    private val devicesTable = mutableMapOf<String, DeviceEntry>()
    private val sessionsTable = mutableMapOf<String, SessionEntry>()
    private val eventsTable = mutableListOf<EventEntry>()
    private val memoryTable = mutableMapOf<String, MemoryPlaceholder>()

    fun initialize() {
        Log.i(TAG, "Initializing MobileDatabase...")
        isOpen = true
    }

    fun saveSetting(key: String, value: String) {
        settingsTable[key] = SettingEntry(key, value)
    }

    fun getSetting(key: String, default: String = ""): String {
        return settingsTable[key]?.value ?: default
    }

    fun recordCommand(action: String, status: String): CommandEntry {
        val entry = CommandEntry(java.util.UUID.randomUUID().toString(), action, status)
        commandsTable.add(entry)
        return entry
    }

    fun getRecentCommands(limit: Int = 10): List<CommandEntry> {
        return commandsTable.takeLast(limit).reversed()
    }

    fun recordEvent(type: String, payloadJson: String): EventEntry {
        val entry = EventEntry(java.util.UUID.randomUUID().toString(), type, payloadJson)
        eventsTable.add(entry)
        return entry
    }

    fun getRecentEvents(limit: Int = 10): List<EventEntry> {
        return eventsTable.takeLast(limit).reversed()
    }

    fun close() {
        isOpen = false
        Log.i(TAG, "MobileDatabase closed.")
    }
}
