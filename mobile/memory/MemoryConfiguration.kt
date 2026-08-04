package com.nova.mobile.memory

data class MemoryConfiguration(
    val autoLearnContacts: Boolean = true,
    val autoLearnApps: Boolean = true,
    val autoLearnPreferences: Boolean = true,
    val autoLearnRoutines: Boolean = false,     // routines require explicit user confirmation
    val contactFrequencyThreshold: Int = 5,     // how many times before marking "favorite"
    val appFrequencyThreshold: Int = 10,
    val commandFrequencyThreshold: Int = 5,
    val preferenceRepeatThreshold: Int = 3,
    val maxRecentCommands: Int = 50,
    val maxMemoryEntries: Int = 1000,
    val encryptAtRest: Boolean = true,
    val syncWithNovaCore: Boolean = false        // off by default — user must opt in
)

data class MemoryStatistics(
    val totalEntries: Int = 0,
    val entriesByCategory: Map<String, Int> = emptyMap(),
    val favoriteContactsCount: Int = 0,
    val favoriteAppsCount: Int = 0,
    val frequentCommandsCount: Int = 0,
    val recentCommandsCount: Int = 0,
    val lastSyncTimestamp: Long = 0L
)
