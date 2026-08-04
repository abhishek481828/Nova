package com.nova.mobile.memory

import android.util.Log
import java.time.Instant

/**
 * MemoryStore — In-memory, thread-safe structured memory storage.
 * Entries are indexed by category and key.
 * Sensitive keys (password, otp, token, secret) are REJECTED with an error log.
 */
class MemoryStore {
    companion object {
        private const val TAG = "MemoryStore"
        private val BLOCKED_KEYS = setOf(
            "password", "passwd", "otp", "token", "secret", "pin", "card_number",
            "bank", "cvv", "ssn", "auth_token", "access_token", "refresh_token"
        )
    }

    // Primary store: category → (key → entry)
    private val store: MutableMap<MemoryCategory, MutableMap<String, MemoryEntry>> =
        MemoryCategory.values().associateWith { mutableMapOf<String, MemoryEntry>() }.toMutableMap()

    fun put(entry: MemoryEntry): Boolean {
        val keyLower = entry.key.lowercase()
        if (BLOCKED_KEYS.any { keyLower.contains(it) }) {
            Log.e(TAG, "BLOCKED: Attempt to store sensitive key '${entry.key}' in memory. Rejected.")
            return false
        }
        val categoryMap = store.getOrPut(entry.category) { mutableMapOf() }
        val existing = categoryMap[entry.key]
        if (existing != null) {
            categoryMap[entry.key] = existing.copy(
                value = entry.value,
                confidence = entry.confidence,
                frequency = existing.frequency + 1,
                updatedAt = Instant.now().epochSecond
            )
        } else {
            categoryMap[entry.key] = entry
        }
        return true
    }

    fun get(category: MemoryCategory, key: String): MemoryEntry? =
        store[category]?.get(key)

    fun getAll(category: MemoryCategory): List<MemoryEntry> =
        store[category]?.values?.toList() ?: emptyList()

    fun getAll(): List<MemoryEntry> =
        store.values.flatMap { it.values }

    fun search(query: String): List<MemoryEntry> {
        val q = query.lowercase()
        return getAll().filter { it.key.lowercase().contains(q) || it.value.lowercase().contains(q) }
    }

    fun delete(category: MemoryCategory, key: String): Boolean {
        return store[category]?.remove(key) != null
    }

    fun deleteCategory(category: MemoryCategory): Int {
        val count = store[category]?.size ?: 0
        store[category]?.clear()
        return count
    }

    fun clear(): Int {
        val total = getAll().size
        store.forEach { (_, map) -> map.clear() }
        return total
    }

    fun totalCount(): Int = store.values.sumOf { it.size }

    fun countByCategory(): Map<String, Int> =
        store.entries.associate { (cat, map) -> cat.name to map.size }

    fun getFrequency(category: MemoryCategory, key: String): Int =
        store[category]?.get(key)?.frequency ?: 0
}
