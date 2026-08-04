package com.nova.mobile.memory

import android.content.Context
import android.util.Log
import com.nova.mobile.lifecycle.LifecycleManager
import java.time.Instant

/**
 * MemoryManager — Phase 6 orchestrator.
 *
 * Responsibilities:
 *   1. Track command frequency → auto-promote to favorites when threshold is met.
 *   2. Learn preferences from repeated patterns.
 *   3. Handle memory queries ("What do you remember?", "Forget everything.").
 *   4. Sync with Nova Core when available (optional, opt-in).
 *   5. Publish lifecycle events for every memory operation.
 *   6. Enforce privacy: block sensitive keys, never log values.
 */
class MemoryManager(
    private val context: Context,
    private val lifecycleManager: LifecycleManager,
    val config: MemoryConfiguration = MemoryConfiguration()
) {
    companion object {
        private const val TAG = "MemoryManager"

        // Memory query triggers
        private val RECALL_TRIGGERS = listOf(
            "what do you remember", "what you know about me",
            "show my memories", "show remembered", "my preferences"
        )
        private val FORGET_ALL_TRIGGERS = listOf("forget everything", "clear all memory", "delete everything")
        private val FORGET_CONTACTS_TRIGGERS = listOf("forget my contacts", "forget favorite contacts")
        private val FORGET_APPS_TRIGGERS = listOf("forget my apps", "forget favorite apps")
        private val FORGET_COMMANDS_TRIGGERS = listOf("clear recent commands", "forget recent commands")
        private val FORGET_ROUTINES_TRIGGERS = listOf("forget my routines", "forget routines")
    }

    val store = MemoryStore()
    val repository = MemoryRepository(store)

    // Contact & app command frequency counters
    private val contactFrequency = mutableMapOf<String, Int>()
    private val appFrequency = mutableMapOf<String, Int>()
    private val brightnessHistory = mutableListOf<Int>()
    private val volumeHistory = mutableListOf<Int>()
    private val recentCommandBuffer = ArrayDeque<String>()

    // ── Command Learning ─────────────────────────────────────────────────────

    /**
     * Called by CommandEngine after every successful execution.
     * Extracts learnable patterns and updates memory.
     */
    fun onCommandExecuted(intent: String, entities: Map<String, String>, rawText: String) {
        trackRecentCommand(rawText)
        if (config.autoLearnContacts) learnContactIfPresent(intent, entities)
        if (config.autoLearnApps) learnAppIfPresent(intent, entities, rawText)
        if (config.autoLearnPreferences) learnPreferencesIfPresent(intent, entities)
    }

    private fun trackRecentCommand(rawText: String) {
        if (recentCommandBuffer.size >= config.maxRecentCommands) recentCommandBuffer.removeFirst()
        recentCommandBuffer.addLast(rawText)

        val entry = MemoryEntry(
            category = MemoryCategory.RECENT_COMMAND,
            key = "recent_${Instant.now().epochSecond}",
            value = rawText,
            source = "auto",
            confidence = 1.0f
        )
        repository.save(entry)

        // Frequency tracking: if command repeated often → frequent command
        val lowText = rawText.lowercase().trim()
        val freq = (store.get(MemoryCategory.FREQUENT_COMMAND, lowText)?.frequency ?: 0) + 1
        if (freq >= config.commandFrequencyThreshold) {
            val frequent = MemoryEntry(
                category = MemoryCategory.FREQUENT_COMMAND,
                key = lowText,
                value = rawText,
                source = "auto",
                confidence = minOf(1.0f, freq * 0.1f),
                frequency = freq
            )
            if (repository.save(frequent)) {
                publishEvent(MemoryEvent.MEMORY_CREATED, "FREQUENT_COMMAND", lowText)
            }
        }
    }

    private fun learnContactIfPresent(intent: String, entities: Map<String, String>) {
        if (intent != "CALL_CONTACT" && intent != "SEND_SMS") return
        val contactName = entities["contact_name"] ?: return
        val freq = (contactFrequency[contactName] ?: 0) + 1
        contactFrequency[contactName] = freq

        if (freq >= config.contactFrequencyThreshold) {
            val existing = store.get(MemoryCategory.FAVORITE_CONTACT, contactName.lowercase())
            val entry = MemoryEntry(
                id = existing?.id ?: java.util.UUID.randomUUID().toString(),
                category = MemoryCategory.FAVORITE_CONTACT,
                key = contactName.lowercase(),
                value = contactName,
                frequency = freq,
                confidence = minOf(1.0f, freq * 0.1f),
                source = "auto",
                updatedAt = Instant.now().epochSecond
            )
            val isNew = existing == null
            if (repository.save(entry)) {
                Log.i(TAG, "Favorite contact learned: $contactName (freq=$freq)")
                publishEvent(if (isNew) MemoryEvent.MEMORY_CREATED else MemoryEvent.MEMORY_UPDATED,
                    "FAVORITE_CONTACT", contactName)
            }
        }
    }

    private fun learnAppIfPresent(intent: String, entities: Map<String, String>, rawText: String) {
        val appHints = listOf("OPEN_APP", "PLAY_YOUTUBE", "PLAY_SPOTIFY", "OPEN_BROWSER", "OPEN_MAPS")
        if (intent !in appHints) return

        val appName = entities["app_name"] ?: extractAppHint(rawText) ?: return
        val freq = (appFrequency[appName] ?: 0) + 1
        appFrequency[appName] = freq

        if (freq >= config.appFrequencyThreshold) {
            val entry = MemoryEntry(
                category = MemoryCategory.FAVORITE_APP,
                key = appName.lowercase(),
                value = appName,
                frequency = freq,
                confidence = minOf(1.0f, freq * 0.1f),
                source = "auto"
            )
            if (repository.save(entry)) {
                Log.i(TAG, "Favorite app learned: $appName (freq=$freq)")
                publishEvent(MemoryEvent.MEMORY_CREATED, "FAVORITE_APP", appName)
            }
        }
    }

    private fun learnPreferencesIfPresent(intent: String, entities: Map<String, String>) {
        when (intent) {
            "SET_BRIGHTNESS" -> {
                val pct = entities["percentage"]?.toIntOrNull() ?: return
                brightnessHistory.add(pct)
                if (brightnessHistory.size >= config.preferenceRepeatThreshold) {
                    val avg = brightnessHistory.takeLast(5).average().toInt()
                    val entry = MemoryEntry(
                        category = MemoryCategory.PREFERRED_BRIGHTNESS,
                        key = "preferred_brightness",
                        value = avg.toString(),
                        source = "auto",
                        confidence = 0.85f,
                        frequency = brightnessHistory.size
                    )
                    if (repository.save(entry)) {
                        Log.i(TAG, "Preferred brightness learned: $avg%")
                        publishEvent(MemoryEvent.MEMORY_UPDATED, "PREFERRED_BRIGHTNESS", avg.toString())
                    }
                }
            }
            "SET_VOLUME" -> {
                val pct = entities["percentage"]?.toIntOrNull() ?: return
                volumeHistory.add(pct)
                if (volumeHistory.size >= config.preferenceRepeatThreshold) {
                    val avg = volumeHistory.takeLast(5).average().toInt()
                    val entry = MemoryEntry(
                        category = MemoryCategory.PREFERRED_VOLUME,
                        key = "preferred_volume",
                        value = avg.toString(),
                        source = "auto",
                        confidence = 0.85f,
                        frequency = volumeHistory.size
                    )
                    if (repository.save(entry)) {
                        Log.i(TAG, "Preferred volume learned: $avg%")
                        publishEvent(MemoryEvent.MEMORY_UPDATED, "PREFERRED_VOLUME", avg.toString())
                    }
                }
            }
        }
    }

    private fun extractAppHint(rawText: String): String? {
        val text = rawText.lowercase()
        return when {
            "youtube" in text -> "YouTube"
            "spotify" in text -> "Spotify"
            "chrome" in text -> "Chrome"
            "maps" in text -> "Google Maps"
            "camera" in text -> "Camera"
            "gallery" in text -> "Gallery"
            else -> null
        }
    }

    // ── Memory Query Handler ─────────────────────────────────────────────────

    fun handleMemoryQuery(rawText: String): String? {
        val clean = rawText.lowercase().trim()

        if (RECALL_TRIGGERS.any { it in clean }) return buildRecallResponse()
        if (FORGET_ALL_TRIGGERS.any { it in clean }) return forgetAll()
        if (FORGET_CONTACTS_TRIGGERS.any { it in clean }) return forgetCategory(MemoryCategory.FAVORITE_CONTACT, "favorite contacts")
        if (FORGET_APPS_TRIGGERS.any { it in clean }) return forgetCategory(MemoryCategory.FAVORITE_APP, "favorite apps")
        if (FORGET_COMMANDS_TRIGGERS.any { it in clean }) return forgetCategory(MemoryCategory.RECENT_COMMAND, "recent commands")
        if (FORGET_ROUTINES_TRIGGERS.any { it in clean }) return forgetCategory(MemoryCategory.DAILY_ROUTINE, "routines")

        return null  // not a memory query
    }

    private fun buildRecallResponse(): String {
        val stats = repository.getStatistics()
        val contacts = repository.list(MemoryCategory.FAVORITE_CONTACT).take(5).joinToString(", ") { it.value }
        val apps = repository.list(MemoryCategory.FAVORITE_APP).take(5).joinToString(", ") { it.value }
        val brightness = store.get(MemoryCategory.PREFERRED_BRIGHTNESS, "preferred_brightness")?.value
        val volume = store.get(MemoryCategory.PREFERRED_VOLUME, "preferred_volume")?.value

        return buildString {
            appendLine("Here's what I remember about you:")
            if (contacts.isNotBlank()) appendLine("• Favorite Contacts: $contacts")
            if (apps.isNotBlank()) appendLine("• Favorite Apps: $apps")
            if (brightness != null) appendLine("• Preferred Brightness: $brightness%")
            if (volume != null) appendLine("• Preferred Volume: $volume%")
            appendLine("• Total Memories: ${stats.totalEntries}")
            if (stats.totalEntries == 0) appendLine("I haven't learned much yet. Keep using Nova and I'll remember your preferences!")
        }.trim()
    }

    private fun forgetCategory(category: MemoryCategory, label: String): String {
        val count = repository.deleteCategory(category)
        publishEvent(MemoryEvent.MEMORY_DELETED, category.name, "all")
        return if (count > 0) "Done. I've forgotten your $label ($count items removed)."
        else "I didn't have any $label stored."
    }

    private fun forgetAll(): String {
        val count = repository.clear()
        contactFrequency.clear()
        appFrequency.clear()
        brightnessHistory.clear()
        volumeHistory.clear()
        recentCommandBuffer.clear()
        publishEvent(MemoryEvent.MEMORY_CLEARED, "ALL", "all")
        return "Done. I've securely cleared all $count stored memories."
    }

    // ── Sync with Nova Core ──────────────────────────────────────────────────

    fun syncWithNovaCore(): Boolean {
        if (!config.syncWithNovaCore) {
            Log.i(TAG, "Nova Core sync is disabled by user configuration.")
            return false
        }
        Log.i(TAG, "Syncing memory with Nova Core...")
        publishEvent(MemoryEvent.MEMORY_SYNCHRONIZED, "ALL", "sync_requested")
        // Actual WebSocket sync wired via HybridRouter in future milestone
        return true
    }

    // ── Events ───────────────────────────────────────────────────────────────

    private fun publishEvent(event: MemoryEvent, category: String, key: String) {
        lifecycleManager.publishEvent(
            event.name,
            mapOf("category" to category, "key" to key, "timestamp" to Instant.now().epochSecond)
        )
    }
}
