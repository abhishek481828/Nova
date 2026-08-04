package com.nova.mobile.skills

import android.util.Log
import java.time.Instant

/**
 * SkillRegistry — Source of truth for all installed and running skills.
 * Stores manifests, instances, granted permissions, and execution history.
 */
class SkillRegistry {
    companion object { private const val TAG = "SkillRegistry" }

    private val skills: MutableMap<String, BaseSkill> = mutableMapOf()
    private val grantedPermissions: MutableMap<String, MutableSet<SkillPermission>> = mutableMapOf()
    private val executionLog: MutableList<String> = mutableListOf()
    private val intentIndex: MutableMap<String, String> = mutableMapOf()  // phrase → skillId

    fun register(skill: BaseSkill): Boolean {
        val validation = skill.manifest.validate()
        if (validation.isFailure) {
            Log.e(TAG, "Manifest validation FAILED for '${skill.manifest.skillId}': ${validation.exceptionOrNull()?.message}")
            return false
        }
        skills[skill.manifest.skillId] = skill
        // Index all intent phrases (lowercase)
        skill.manifest.intentPhrases.forEach { phrase ->
            intentIndex[phrase.lowercase()] = skill.manifest.skillId
        }
        Log.i(TAG, "Registered skill: '${skill.manifest.name}' v${skill.manifest.version}")
        return true
    }

    fun unregister(skillId: String): Boolean {
        val skill = skills.remove(skillId) ?: return false
        skill.manifest.intentPhrases.forEach { intentIndex.remove(it.lowercase()) }
        grantedPermissions.remove(skillId)
        Log.i(TAG, "Unregistered skill: $skillId")
        return true
    }

    fun get(skillId: String): BaseSkill? = skills[skillId]

    fun getAll(): List<BaseSkill> = skills.values.toList()

    fun getEnabled(): List<BaseSkill> =
        skills.values.filter { it.status == SkillStatus.LOADED || it.status == SkillStatus.RUNNING }

    fun findByIntent(text: String): BaseSkill? {
        val low = text.lowercase()
        // First try exact phrase lookup
        intentIndex.entries.firstOrNull { (phrase, _) -> phrase in low }
            ?.let { (_, id) -> return skills[id] }
        // Then ask each enabled skill
        return getEnabled().firstOrNull { it.canHandle(text) }
    }

    fun grantPermission(skillId: String, permission: SkillPermission) {
        grantedPermissions.getOrPut(skillId) { mutableSetOf() }.add(permission)
        audit("GRANTED ${permission.name} to '$skillId'")
    }

    fun revokePermission(skillId: String, permission: SkillPermission) {
        grantedPermissions[skillId]?.remove(permission)
        audit("REVOKED ${permission.name} from '$skillId'")
    }

    fun getGrantedPermissions(skillId: String): Set<SkillPermission> =
        grantedPermissions[skillId] ?: emptySet()

    fun count(): Int = skills.size
    fun countEnabled(): Int = getEnabled().size
    fun getIntentIndex(): Map<String, String> = intentIndex.toMap()
    fun getAuditLog(): List<String> = executionLog.toList()

    private fun audit(message: String) {
        val entry = "[${Instant.now()}] $message"
        executionLog.add(entry)
        Log.i(TAG, entry)
        if (executionLog.size > 500) executionLog.removeAt(0)
    }
}
