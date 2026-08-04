package com.nova.mobile.skills

/**
 * SkillContext — Official API surface exposed to every skill.
 * Skills interact with Nova ONLY through this context.
 * Direct access to internal components is not permitted.
 */
class SkillContext(
    val skillId: String,
    private val grantedPermissions: Set<SkillPermission>,
    // Nova API stubs — injected by SkillManager at load time
    val memoryApi: SkillMemoryApi? = null,
    val notificationApi: SkillNotificationApi? = null,
    val schedulerApi: SkillSchedulerApi? = null,
    val voiceApi: SkillVoiceApi? = null
) {
    fun hasPermission(permission: SkillPermission): Boolean =
        permission in grantedPermissions

    fun requirePermission(permission: SkillPermission) {
        check(hasPermission(permission)) {
            "Skill '$skillId' does not have permission: ${permission.name}"
        }
    }
}

/** Minimal API stubs — expanded in SkillManager injection. */
interface SkillMemoryApi {
    fun remember(key: String, value: String)
    fun recall(key: String): String?
    fun forget(key: String)
}

interface SkillNotificationApi {
    fun notify(title: String, body: String)
}

interface SkillSchedulerApi {
    fun scheduleOnce(delayMs: Long, action: () -> Unit)
}

interface SkillVoiceApi {
    fun speak(text: String)
}
