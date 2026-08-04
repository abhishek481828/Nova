package com.nova.mobile.skills

import android.util.Log
import java.time.Instant

/**
 * SkillExecutor — Routes incoming voice text to the correct skill.
 *
 * Priority:
 *   1. Exact intent phrase match (registry index)
 *   2. Skill.canHandle() check on all running skills
 *   3. No match → returns null
 *
 * Records execution timing and logs to the audit trail.
 */
class SkillExecutor(private val registry: SkillRegistry) {
    companion object { private const val TAG = "SkillExecutor" }

    private val executionHistory: MutableList<SkillExecutionResult> = mutableListOf()

    fun execute(text: String): SkillExecutionResult? {
        val skill = registry.findByIntent(text)
        if (skill == null) {
            Log.d(TAG, "No skill matched for: '$text'")
            return null
        }

        if (skill.status != SkillStatus.RUNNING) {
            Log.w(TAG, "Skill '${skill.manifest.skillId}' matched but is not RUNNING (${skill.status})")
            return null
        }

        val start = System.currentTimeMillis()
        Log.i(TAG, "→ Executing '${skill.manifest.name}' for: '$text'")

        val result = try {
            skill.execute(text)
        } catch (e: Exception) {
            Log.e(TAG, "Skill '${skill.manifest.skillId}' threw exception: ${e.message}", e)
            SkillExecutionResult(
                skillId = skill.manifest.skillId,
                isSuccess = false,
                spokenResponse = "Sorry, the ${skill.manifest.name} skill encountered an error.",
                errorMessage = e.message,
                durationMs = System.currentTimeMillis() - start
            )
        }

        val timed = result.copy(durationMs = System.currentTimeMillis() - start)
        record(timed)
        Log.i(TAG, "← '${skill.manifest.name}' finished in ${timed.durationMs}ms [${if (timed.isSuccess) "OK" else "FAIL"}]")
        return timed
    }

    fun getHistory(): List<SkillExecutionResult> = executionHistory.toList().reversed()

    fun getLastResult(): SkillExecutionResult? = executionHistory.lastOrNull()

    fun totalExecutions(): Int = executionHistory.size

    fun failureCount(): Int = executionHistory.count { !it.isSuccess }

    private fun record(result: SkillExecutionResult) {
        executionHistory.add(result)
        if (executionHistory.size > 200) executionHistory.removeAt(0)
    }
}
