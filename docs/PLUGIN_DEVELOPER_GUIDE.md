# Nova v3.0 — Plugin Developer Guide

## Overview
Nova Plugins extend low-level device capabilities (e.g. Flashlight, Camera, SMS, Audio, System Settings).

## Creating a Plugin

### 1. Kotlin Implementation (`mobile/plugins/`)
Extend `BasePlugin` and define plugin metadata:

```kotlin
package com.nova.mobile.plugins

class FlashlightPlugin : BasePlugin() {
    override val pluginId = "nova.plugin.flashlight"
    override val name = "Flashlight Plugin"
    override val version = "1.0.0"

    override fun onInitialize(): Boolean {
        // Setup camera manager
        return true
    }

    override fun executeAction(action: String, params: Map<String, Any>): PluginActionResult {
        return when (action) {
            "TURN_ON" -> {
                setTorch(true)
                PluginActionResult.success("Flashlight turned on")
            }
            "TURN_OFF" -> {
                setTorch(false)
                PluginActionResult.success("Flashlight turned off")
            }
            else -> PluginActionResult.failure("Unknown action: $action")
        }
    }
}
```

### 2. Registering with `PluginManager`
```kotlin
val pluginManager = MobileCoreManager.pluginManager
pluginManager.registerPlugin(FlashlightPlugin())
```

---

## Guidelines
- Always return a clean `PluginActionResult`.
- Catch all hardware-level exceptions inside `executeAction()` to prevent crashes.
- Request minimum Android permissions required in `AndroidManifest.xml`.
