package com.nova.mobile.automation

import android.util.Log

/**
 * AutomationRepository — Stores and manages all user-created Routines.
 * Supports: create, read, update, delete, enable, disable, duplicate, export, import.
 * All routines are user-created — Nova never invents routines automatically.
 */
class AutomationRepository {
    companion object { private const val TAG = "AutomationRepository" }

    private val routines: MutableMap<String, Routine> = mutableMapOf()

    fun save(routine: Routine): Boolean {
        return try {
            routines[routine.id] = routine
            Log.i(TAG, "Routine saved: '${routine.name}' [${routine.id}]")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to save routine: ${e.message}")
            false
        }
    }

    fun get(id: String): Routine? = routines[id]

    fun getAll(): List<Routine> = routines.values.toList()

    fun getEnabled(): List<Routine> = routines.values.filter { it.status == AutomationStatus.ENABLED }

    fun delete(id: String): Boolean {
        val removed = routines.remove(id) != null
        if (removed) Log.i(TAG, "Routine deleted: $id")
        return removed
    }

    fun setStatus(id: String, status: AutomationStatus): Boolean {
        val routine = routines[id] ?: return false
        routines[id] = routine.copy(status = status)
        Log.i(TAG, "Routine '$id' status → $status")
        return true
    }

    fun duplicate(id: String): Routine? {
        val original = routines[id] ?: return null
        val copy = original.copy(
            id = java.util.UUID.randomUUID().toString(),
            name = "${original.name} (Copy)",
            status = AutomationStatus.DISABLED,
            createdAt = java.time.Instant.now().epochSecond
        )
        routines[copy.id] = copy
        Log.i(TAG, "Routine duplicated: '${copy.name}' [${copy.id}]")
        return copy
    }

    fun recordExecution(id: String): Boolean {
        val routine = routines[id] ?: return false
        routines[id] = routine.copy(
            lastExecutedAt = java.time.Instant.now().epochSecond,
            executionCount = routine.executionCount + 1
        )
        return true
    }

    fun export(): List<Map<String, Any>> = routines.values.map { r ->
        mapOf(
            "id" to r.id, "name" to r.name, "description" to r.description,
            "status" to r.status.name, "execution_count" to r.executionCount,
            "created_at" to r.createdAt, "actions_count" to r.actions.size
        )
    }

    fun count(): Int = routines.size
    fun countEnabled(): Int = getEnabled().size
}
