# Nova v3.0 — AI Skill Developer Guide

## Overview
Nova Skills provide high-level voice interaction features (e.g. Weather, Calculator, Translator, Notes). Skills run in a sandboxed execution context and interact with Nova solely via `SkillContext`.

---

## Creating an AI Skill

### 1. Define Skill Class (`mobile/skills/` or Python `nova/mobile/skills/`)

```kotlin
package com.nova.mobile.skills.custom

import com.nova.mobile.skills.*

class HomeAutomationSkill : BaseSkill() {
    override val manifest = SkillManifest(
        skillId = "com.example.home_automation",
        name = "Home Automation",
        description = "Controls smart lights and switches",
        version = "1.0.0",
        author = "Developer Name",
        category = SkillCategory.HOME_AUTOMATION,
        permissions = setOf(SkillPermission.NETWORK),
        intentPhrases = listOf("turn on living room lights", "turn off lights")
    )

    override fun canHandle(text: String): Boolean {
        val t = text.lowercase()
        return "lights" in t || "living room" in t
    }

    override fun execute(text: String): SkillExecutionResult {
        val t = text.lowercase()
        return if ("turn on" in t) {
            // Call API via context
            context.notificationApi?.notify("Home Automation", "Turning on lights...")
            SkillExecutionResult(manifest.skillId, true, "Living room lights turned on.")
        } else {
            SkillExecutionResult(manifest.skillId, true, "Living room lights turned off.")
        }
    }
}
```

### 2. Loading Skill via `SkillManager`
```kotlin
val skillManager = core.skillManager
skillManager.installAndLoad(HomeAutomationSkill())
```

---

## Permission Sandboxing
If your skill requires sensitive permissions (`CAMERA`, `LOCATION`, `CONTACTS`, `SMS`, `MICROPHONE`, `ACCESSIBILITY`), Nova will automatically hold them in a pending queue until approved by the user.
