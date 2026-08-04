package com.nova.mobile.memory

/**
 * PersonalMemoryStore — Public facade for the Nova Mobile memory system.
 * Delegates all operations to MemoryManager.
 * Retained for backward compatibility with any Phase 1 references.
 */
class PersonalMemoryStore(val manager: MemoryManager) {
    fun getMemoryCount(): Int = manager.store.totalCount()
    fun getStatistics(): MemoryStatistics = manager.repository.getStatistics()
    fun list(category: MemoryCategory? = null): List<MemoryEntry> = manager.repository.list(category)
    fun search(query: String): List<MemoryEntry> = manager.repository.search(query)
}
