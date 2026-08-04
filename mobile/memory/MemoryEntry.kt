package com.nova.mobile.memory

import java.time.Instant

/**
 * MemoryEntry — A single structured personal memory record.
 *
 * Every entry must have:
 *   - id, category, key, value, confidence
 *   - createdAt, updatedAt, source, frequency
 *   - isUserEditable, isUserDeletable
 *
 * Sensitive values (passwords, OTPs, tokens) are NEVER stored here.
 */
data class MemoryEntry(
    val id: String = java.util.UUID.randomUUID().toString(),
    val category: MemoryCategory,
    val key: String,            // e.g. "favorite_contact", "preferred_brightness"
    val value: String,          // e.g. "Pankaj", "70"
    val confidence: Float = 1.0f,   // 0.0–1.0
    val source: String = "auto",    // "auto" | "user_set"
    val frequency: Int = 1,
    val createdAt: Long = Instant.now().epochSecond,
    val updatedAt: Long = Instant.now().epochSecond,
    val isUserEditable: Boolean = true,
    val isUserDeletable: Boolean = true,
    val isEncrypted: Boolean = true
)
