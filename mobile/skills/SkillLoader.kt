package com.nova.mobile.skills

import android.util.Log

/**
 * SkillLoader — Manages the full lifecycle state machine for skills.
 *
 * Transitions:
 *   NOT_INSTALLED → INSTALLED → LOADING → LOADED → RUNNING ↔ DISABLED
 *                                                          → UNLOADING → NOT_INSTALLED
 */
class SkillLoader(private val registry: SkillRegistry) {
    companion object { private const val TAG = "SkillLoader" }

    fun install(skill: BaseSkill, context: SkillContext): Boolean {
        skill.context = context
        skill.status = SkillStatus.INSTALLED
        return registry.register(skill)
    }

    fun load(skillId: String): Boolean {
        val skill = registry.get(skillId) ?: return false
        if (skill.status == SkillStatus.LOADED || skill.status == SkillStatus.RUNNING) return true
        return try {
            skill.status = SkillStatus.LOADING
            skill.onCreate()
            skill.status = SkillStatus.LOADED
            Log.i(TAG, "Loaded: '${skill.manifest.name}'")
            true
        } catch (e: Exception) {
            skill.status = SkillStatus.ERROR
            Log.e(TAG, "Failed to load '${skill.manifest.skillId}': ${e.message}")
            false
        }
    }

    fun enable(skillId: String): Boolean {
        val skill = registry.get(skillId) ?: return false
        if (skill.status == SkillStatus.RUNNING) return true
        return try {
            skill.onEnable()
            skill.status = SkillStatus.RUNNING
            Log.i(TAG, "Enabled: '${skill.manifest.name}'")
            true
        } catch (e: Exception) {
            skill.status = SkillStatus.ERROR
            Log.e(TAG, "Enable failed '${skill.manifest.skillId}': ${e.message}")
            false
        }
    }

    fun disable(skillId: String): Boolean {
        val skill = registry.get(skillId) ?: return false
        return try {
            skill.onDisable()
            skill.status = SkillStatus.DISABLED
            Log.i(TAG, "Disabled: '${skill.manifest.name}'")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Disable failed '${skill.manifest.skillId}': ${e.message}")
            false
        }
    }

    fun unload(skillId: String): Boolean {
        val skill = registry.get(skillId) ?: return false
        return try {
            skill.status = SkillStatus.UNLOADING
            skill.onDestroy()
            registry.unregister(skillId)
            Log.i(TAG, "Unloaded: '$skillId'")
            true
        } catch (e: Exception) {
            skill.status = SkillStatus.ERROR
            Log.e(TAG, "Unload failed '$skillId': ${e.message}")
            false
        }
    }

    fun hotReload(skill: BaseSkill, context: SkillContext): Boolean {
        val id = skill.manifest.skillId
        Log.i(TAG, "Hot-reloading: '$id'")
        unload(id)
        return install(skill, context) && load(id) && enable(id)
    }
}
