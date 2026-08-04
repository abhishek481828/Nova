package com.nova.mobile.skills

import android.util.Log
import com.nova.mobile.lifecycle.LifecycleManager

/**
 * SkillManager — Phase 9 Main Orchestrator.
 *
 * Responsibilities:
 *   1. Install, load, enable, disable, unload, remove skills
 *   2. Auto-grant non-sensitive permissions
 *   3. Queue sensitive permissions for user approval
 *   4. Route voice queries to the correct skill via SkillExecutor
 *   5. Publish lifecycle events for all operations
 *   6. Provide local skill catalog browsing
 *   7. Enforce sandbox: skills interact only through SkillContext
 */
class SkillManager(private val lifecycleManager: LifecycleManager) {
    companion object { private const val TAG = "SkillManager" }

    val registry = SkillRegistry()
    val loader = SkillLoader(registry)
    val executor = SkillExecutor(registry)

    private val pendingPermissions: MutableMap<String, MutableSet<SkillPermission>> = mutableMapOf()
    private var memoryApi: SkillMemoryApi? = null
    private var notificationApi: SkillNotificationApi? = null
    private var schedulerApi: SkillSchedulerApi? = null
    private var voiceApi: SkillVoiceApi? = null

    // ── API Injection ──────────────────────────────────────────────────────────

    fun setMemoryApi(api: SkillMemoryApi) { memoryApi = api }
    fun setNotificationApi(api: SkillNotificationApi) { notificationApi = api }
    fun setSchedulerApi(api: SkillSchedulerApi) { schedulerApi = api }
    fun setVoiceApi(api: SkillVoiceApi) { voiceApi = api }

    // ── Install / Remove ──────────────────────────────────────────────────────

    fun installAndLoad(skill: BaseSkill): Boolean {
        val validation = skill.manifest.validate()
        if (validation.isFailure) {
            Log.e(TAG, "Rejected invalid skill: ${validation.exceptionOrNull()?.message}")
            return false
        }

        val grantedPermissions = processPermissions(skill)
        val context = SkillContext(
            skillId = skill.manifest.skillId,
            grantedPermissions = grantedPermissions,
            memoryApi = memoryApi,
            notificationApi = notificationApi,
            schedulerApi = schedulerApi,
            voiceApi = voiceApi
        )

        val installed = loader.install(skill, context)
        if (!installed) return false

        val loaded = loader.load(skill.manifest.skillId)
        if (!loaded) return false

        val enabled = loader.enable(skill.manifest.skillId)
        lifecycleManager.publishEvent("SkillInstalled",
            mapOf("skillId" to skill.manifest.skillId, "name" to skill.manifest.name))
        Log.i(TAG, "Skill fully installed and running: '${skill.manifest.name}'")
        return enabled
    }

    fun remove(skillId: String): Boolean {
        val ok = loader.unload(skillId)
        if (ok) lifecycleManager.publishEvent("SkillRemoved", mapOf("skillId" to skillId))
        return ok
    }

    fun enable(skillId: String): Boolean {
        val ok = loader.enable(skillId)
        if (ok) lifecycleManager.publishEvent("SkillEnabled", mapOf("skillId" to skillId))
        return ok
    }

    fun disable(skillId: String): Boolean {
        val ok = loader.disable(skillId)
        if (ok) lifecycleManager.publishEvent("SkillDisabled", mapOf("skillId" to skillId))
        return ok
    }

    // ── Voice Routing ─────────────────────────────────────────────────────────

    /** Called by CommandEngine when built-in intents don't match. */
    fun handleVoiceText(text: String): SkillExecutionResult? =
        executor.execute(text)

    // ── Permission Handling ───────────────────────────────────────────────────

    private fun processPermissions(skill: BaseSkill): Set<SkillPermission> {
        val granted = mutableSetOf<SkillPermission>()
        for (permission in skill.manifest.permissions) {
            if (permission.requiresUserApproval) {
                pendingPermissions.getOrPut(skill.manifest.skillId) { mutableSetOf() }
                    .add(permission)
                Log.i(TAG, "Permission '${permission.name}' for '${skill.manifest.name}' requires user approval")
            } else {
                granted.add(permission)
                registry.grantPermission(skill.manifest.skillId, permission)
            }
        }
        return granted
    }

    fun approvePermission(skillId: String, permission: SkillPermission): Boolean {
        registry.grantPermission(skillId, permission)
        pendingPermissions[skillId]?.remove(permission)
        lifecycleManager.publishEvent("SkillPermissionGranted",
            mapOf("skillId" to skillId, "permission" to permission.name))
        return true
    }

    fun denyPermission(skillId: String, permission: SkillPermission) {
        pendingPermissions[skillId]?.remove(permission)
        lifecycleManager.publishEvent("SkillPermissionDenied",
            mapOf("skillId" to skillId, "permission" to permission.name))
    }

    fun getPendingPermissions(): Map<String, Set<SkillPermission>> =
        pendingPermissions.mapValues { it.value.toSet() }

    // ── Catalog ───────────────────────────────────────────────────────────────

    fun getInstalledSkills(): List<BaseSkill> = registry.getAll()

    fun getRunningSkills(): List<BaseSkill> = registry.getEnabled()

    fun searchSkills(query: String): List<BaseSkill> {
        val q = query.lowercase()
        return registry.getAll().filter {
            q in it.manifest.name.lowercase() ||
            q in it.manifest.description.lowercase() ||
            q in it.manifest.category.name.lowercase()
        }
    }

    // ── Stats ─────────────────────────────────────────────────────────────────

    fun getStats(): Map<String, Any> = mapOf(
        "total_skills" to registry.count(),
        "running_skills" to registry.countEnabled(),
        "total_executions" to executor.totalExecutions(),
        "failed_executions" to executor.failureCount(),
        "registered_intents" to registry.getIntentIndex().size,
        "pending_permissions" to pendingPermissions.values.sumOf { it.size }
    )
}
