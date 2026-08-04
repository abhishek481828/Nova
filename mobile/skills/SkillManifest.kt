package com.nova.mobile.skills

/**
 * SkillManifest — Declares a skill's metadata, permissions, and voice intent phrases.
 * Every skill must provide a valid manifest before it can be loaded.
 */
data class SkillManifest(
    val skillId: String,
    val name: String,
    val description: String,
    val version: String,
    val author: String,
    val category: SkillCategory,
    val permissions: Set<SkillPermission> = emptySet(),
    val supportedPlatforms: Set<String> = setOf("ANDROID"),
    val dependencies: List<String> = emptyList(),
    val minNovaVersion: String = "3.0.0",
    val maxNovaVersion: String = "4.0.0",
    val entryPoint: String = "",               // fully-qualified class name
    val intentPhrases: List<String> = emptyList(), // voice triggers this skill handles
    val isFirstParty: Boolean = false,
    val isEnabled: Boolean = true
) {
    fun validate(): Result<Unit> {
        if (skillId.isBlank()) return Result.failure(IllegalArgumentException("Skill ID must not be blank"))
        if (name.isBlank()) return Result.failure(IllegalArgumentException("Name must not be blank"))
        if (version.isBlank()) return Result.failure(IllegalArgumentException("Version must not be blank"))
        if (author.isBlank()) return Result.failure(IllegalArgumentException("Author must not be blank"))
        if (skillId.contains(" ")) return Result.failure(IllegalArgumentException("Skill ID must not contain spaces"))
        return Result.success(Unit)
    }
}
