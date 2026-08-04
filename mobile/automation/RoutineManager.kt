package com.nova.mobile.automation

import android.util.Log

/**
 * RoutineManager — User-facing CRUD for Routines.
 * Voice query handler: "What routines do I have?", "Enable driving routine."
 * All mutations require explicit user action — Nova never auto-creates routines.
 */
class RoutineManager(
    private val repository: AutomationRepository,
    private val triggerManager: TriggerManager
) {
    companion object {
        private const val TAG = "RoutineManager"

        private val LIST_TRIGGERS = listOf("what routines", "list routines", "show routines", "my routines")
        private val PAUSE_ALL_TRIGGERS = listOf("pause all", "pause automations", "stop all routines")
        private val RESUME_ALL_TRIGGERS = listOf("resume all", "enable all routines", "resume automations")
    }

    var allPaused: Boolean = false
        private set

    // ── CRUD ──────────────────────────────────────────────────────────────────

    fun createRoutine(routine: Routine): Boolean {
        val saved = repository.save(routine)
        if (saved) Log.i(TAG, "Routine created: '${routine.name}'")
        return saved
    }

    fun updateRoutine(updated: Routine): Boolean = repository.save(updated)

    fun deleteRoutine(id: String): Boolean = repository.delete(id)

    fun enableRoutine(id: String): Boolean = repository.setStatus(id, AutomationStatus.ENABLED)

    fun disableRoutine(id: String): Boolean = repository.setStatus(id, AutomationStatus.DISABLED)

    fun duplicateRoutine(id: String): Routine? = repository.duplicate(id)

    fun getAll(): List<Routine> = repository.getAll()

    fun getEnabled(): List<Routine> = repository.getEnabled()

    fun pauseAll() {
        allPaused = true
        repository.getEnabled().forEach { repository.setStatus(it.id, AutomationStatus.PAUSED) }
        Log.i(TAG, "All automations paused by user")
    }

    fun resumeAll() {
        allPaused = false
        repository.getAll().filter { it.status == AutomationStatus.PAUSED }
            .forEach { repository.setStatus(it.id, AutomationStatus.ENABLED) }
        Log.i(TAG, "All automations resumed")
    }

    // ── Voice Query Handler ───────────────────────────────────────────────────

    fun handleVoiceQuery(rawText: String): String? {
        val clean = rawText.lowercase().trim()

        if (LIST_TRIGGERS.any { it in clean }) return buildRoutineListResponse()
        if (PAUSE_ALL_TRIGGERS.any { it in clean }) {
            pauseAll()
            return "All automations have been paused."
        }
        if (RESUME_ALL_TRIGGERS.any { it in clean }) {
            resumeAll()
            return "All automations have been resumed."
        }

        // "Enable my driving routine" / "Disable sleep routine"
        for (routine in repository.getAll()) {
            val nameLower = routine.name.lowercase()
            when {
                ("enable" in clean || "activate" in clean) && nameLower in clean -> {
                    enableRoutine(routine.id)
                    return "Done. '${routine.name}' is now enabled."
                }
                ("disable" in clean || "turn off" in clean) && nameLower in clean -> {
                    disableRoutine(routine.id)
                    return "Done. '${routine.name}' is now disabled."
                }
                ("delete" in clean || "remove" in clean) && nameLower in clean -> {
                    deleteRoutine(routine.id)
                    return "Done. I've deleted your '${routine.name}' routine."
                }
                ("run" in clean || "execute" in clean || "start" in clean) && nameLower in clean -> {
                    triggerManager.triggerManual(routine.id)
                    return "Running '${routine.name}' now."
                }
            }
        }
        return null
    }

    private fun buildRoutineListResponse(): String {
        val all = repository.getAll()
        if (all.isEmpty()) return "You don't have any routines yet. You can create one by saying 'Create a morning routine'."
        return buildString {
            appendLine("You have ${all.size} routine${if (all.size > 1) "s" else ""}:")
            all.forEach { r ->
                val status = when (r.status) {
                    AutomationStatus.ENABLED -> "🟢 enabled"
                    AutomationStatus.DISABLED -> "⚪ disabled"
                    AutomationStatus.PAUSED -> "⏸ paused"
                    else -> r.status.name.lowercase()
                }
                appendLine("• ${r.name} — $status (${r.actions.size} actions, ran ${r.executionCount}×)")
            }
        }.trim()
    }
}
