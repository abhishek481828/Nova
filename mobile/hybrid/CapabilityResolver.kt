package com.nova.mobile.hybrid

import android.util.Log

/**
 * CapabilityResolver — Maintains the registry of what can be executed locally
 * on Android vs. what requires Nova Core (laptop).
 *
 * Phone Capabilities: calls, sms, camera, flashlight, brightness, volume,
 *   gallery, maps, accessibility, notifications, clipboard, media.
 *
 * Nova Core Capabilities: LLM, coding, browser automation, file analysis,
 *   project search, document processing, long reasoning, desktop automation.
 */
class CapabilityResolver {
    companion object {
        private const val TAG = "CapabilityResolver"

        private val PHONE_INTENTS = setOf(
            "CALL_CONTACT",
            "SEND_SMS",
            "OPEN_APP",
            "PLAY_YOUTUBE",
            "PLAY_SPOTIFY",
            "SET_VOLUME",
            "SET_BRIGHTNESS",
            "FLASHLIGHT_ON",
            "FLASHLIGHT_OFF",
            "OPEN_CAMERA",
            "TAKE_PHOTO",
            "OPEN_SETTINGS",
            "OPEN_MAPS",
            "SET_ALARM",
            "SET_TIMER",
            "SHOW_NOTIFICATIONS",
            "READ_NOTIFICATIONS",
            "OPEN_BROWSER",
            "SEARCH_GOOGLE",
            "OPEN_GALLERY",
            "COPY_TEXT",
            "PASTE_TEXT",
            "DEVICE_STATUS",
            "BATTERY_STATUS"
        )

        private val NOVA_CORE_KEYWORDS = setOf(
            "explain", "summarize", "summary", "analyze", "analyse",
            "write code", "debug", "generate", "translate", "research",
            "what is", "how does", "why does", "define", "tell me about",
            "search the web", "browse", "open file", "read pdf", "read document",
            "project", "automate", "script", "process", "calculate complex",
            "reason", "compare", "difference between", "quantum", "philosophy",
            "history of", "science", "math", "algorithm", "data structure"
        )
    }

    fun resolveTarget(intentName: String, rawText: String): ExecutionTarget {
        val clean = rawText.trim().lowercase()

        // 1. Explicit phone intent → always local
        if (intentName in PHONE_INTENTS && intentName != "UNKNOWN") {
            Log.i(TAG, "[$intentName] resolved to LOCAL_ANDROID via intent registry")
            return ExecutionTarget.LOCAL_ANDROID
        }

        // 2. Text contains Nova Core keywords → forward to laptop
        for (keyword in NOVA_CORE_KEYWORDS) {
            if (keyword in clean) {
                Log.i(TAG, "[$intentName] resolved to NOVA_CORE via keyword '$keyword'")
                return ExecutionTarget.NOVA_CORE
            }
        }

        // 3. Default: local
        Log.i(TAG, "[$intentName] resolved to LOCAL_ANDROID (default)")
        return ExecutionTarget.LOCAL_ANDROID
    }

    fun isPhoneCapability(intentName: String): Boolean = intentName in PHONE_INTENTS
    fun isNovaCoreRequired(rawText: String): Boolean {
        val clean = rawText.trim().lowercase()
        return NOVA_CORE_KEYWORDS.any { it in clean }
    }
}
