package com.nova.mobile.skills

data class SkillExecutionResult(
    val skillId: String,
    val isSuccess: Boolean,
    val spokenResponse: String,
    val errorMessage: String? = null,
    val durationMs: Long = 0L
)

/**
 * BaseSkill — Abstract base class all skills must extend.
 * Provides manifest, context, and a standardised execute() contract.
 */
abstract class BaseSkill {
    abstract val manifest: SkillManifest

    lateinit var context: SkillContext
        internal set

    var status: SkillStatus = SkillStatus.NOT_INSTALLED
        internal set

    /** Called once when the skill is loaded. */
    open fun onCreate() {}

    /** Called when the skill is enabled after being disabled. */
    open fun onEnable() {}

    /** Called when the skill is disabled. */
    open fun onDisable() {}

    /** Called before the skill is unloaded/removed. */
    open fun onDestroy() {}

    /** Returns true if this skill can handle the given text. */
    abstract fun canHandle(text: String): Boolean

    /** Execute the skill for the given input and return a spoken response. */
    abstract fun execute(text: String): SkillExecutionResult
}
