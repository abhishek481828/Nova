package com.nova.mobile.memory

import android.util.Log

/**
 * MemoryRepository — CRUD interface over MemoryStore.
 * Supports: list, search, export, import, delete, clear.
 */
class MemoryRepository(private val store: MemoryStore) {
    companion object { private const val TAG = "MemoryRepository" }

    fun list(category: MemoryCategory? = null): List<MemoryEntry> =
        if (category != null) store.getAll(category) else store.getAll()

    fun search(query: String): List<MemoryEntry> = store.search(query)

    fun find(category: MemoryCategory, key: String): MemoryEntry? = store.get(category, key)

    fun save(entry: MemoryEntry): Boolean {
        val ok = store.put(entry)
        if (ok) Log.i(TAG, "Memory saved: [${entry.category.name}] ${entry.key} = ${entry.value}")
        return ok
    }

    fun delete(category: MemoryCategory, key: String): Boolean {
        val ok = store.delete(category, key)
        if (ok) Log.i(TAG, "Memory deleted: [${category.name}] $key")
        return ok
    }

    fun deleteCategory(category: MemoryCategory): Int {
        val count = store.deleteCategory(category)
        Log.i(TAG, "Memory category cleared: ${category.name} ($count entries removed)")
        return count
    }

    fun clear(): Int {
        val count = store.clear()
        Log.i(TAG, "All memory cleared: $count entries removed")
        return count
    }

    fun export(): List<Map<String, Any>> = store.getAll().map { entry ->
        mapOf(
            "id" to entry.id,
            "category" to entry.category.name,
            "key" to entry.key,
            "value" to entry.value,
            "confidence" to entry.confidence,
            "frequency" to entry.frequency,
            "source" to entry.source,
            "created_at" to entry.createdAt,
            "updated_at" to entry.updatedAt
        )
    }

    fun import(records: List<MemoryEntry>): Int {
        var imported = 0
        records.forEach { entry ->
            if (store.put(entry)) imported++
        }
        Log.i(TAG, "Memory import complete: $imported entries imported")
        return imported
    }

    fun getStatistics(): MemoryStatistics {
        val byCategory = store.countByCategory()
        return MemoryStatistics(
            totalEntries = store.totalCount(),
            entriesByCategory = byCategory,
            favoriteContactsCount = store.getAll(MemoryCategory.FAVORITE_CONTACT).size,
            favoriteAppsCount = store.getAll(MemoryCategory.FAVORITE_APP).size,
            frequentCommandsCount = store.getAll(MemoryCategory.FREQUENT_COMMAND).size,
            recentCommandsCount = store.getAll(MemoryCategory.RECENT_COMMAND).size
        )
    }
}
