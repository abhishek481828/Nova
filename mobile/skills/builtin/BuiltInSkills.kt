package com.nova.mobile.skills.builtin

import com.nova.mobile.skills.*
import kotlin.math.*

class CalculatorSkill : BaseSkill() {
    override val manifest = SkillManifest(
        skillId = "nova.builtin.calculator",
        name = "Calculator",
        description = "Evaluates math expressions from voice commands",
        version = "1.0.0",
        author = "Nova First Party",
        category = SkillCategory.UTILITIES,
        isFirstParty = true,
        intentPhrases = listOf("calculate", "what is", "how much is", "compute", "solve"),
        permissions = emptySet()
    )

    override fun canHandle(text: String): Boolean {
        val t = text.lowercase()
        return listOf("calculate", "what is", "how much is", "compute", "solve", "plus", "minus",
            "times", "divided", "percent").any { t.contains(it) } &&
            text.any { it.isDigit() }
    }

    override fun execute(text: String): SkillExecutionResult {
        val expr = extractExpression(text)
        return try {
            val result = evaluate(expr)
            SkillExecutionResult(manifest.skillId, true,
                "The answer is ${if (result == result.toLong().toDouble()) result.toLong() else result}")
        } catch (e: Exception) {
            SkillExecutionResult(manifest.skillId, false, "I couldn't calculate that.", errorMessage = e.message)
        }
    }

    private fun extractExpression(text: String): String =
        text.replace(Regex("(?i)(calculate|compute|solve|what is|how much is)"), "")
            .replace("plus", "+").replace("minus", "-")
            .replace(Regex("times|multiplied by"), "*")
            .replace(Regex("divided by|over"), "/")
            .replace("percent", "/100").trim()

    private fun evaluate(expr: String): Double {
        // Simple stack-based evaluator for +,-,*,/
        val tokens = expr.replace(" ", "").split(Regex("(?<=[+\\-*/])|(?=[+\\-*/])"))
        var result = tokens[0].toDouble()
        var i = 1
        while (i < tokens.size - 1) {
            val op = tokens[i]
            val operand = tokens[i + 1].toDouble()
            result = when (op) {
                "+" -> result + operand
                "-" -> result - operand
                "*" -> result * operand
                "/" -> if (operand == 0.0) throw ArithmeticException("Division by zero") else result / operand
                else -> result
            }
            i += 2
        }
        return result
    }
}

class UnitConverterSkill : BaseSkill() {
    override val manifest = SkillManifest(
        skillId = "nova.builtin.unit_converter",
        name = "Unit Converter",
        description = "Converts between common units of measurement",
        version = "1.0.0",
        author = "Nova First Party",
        category = SkillCategory.UTILITIES,
        isFirstParty = true,
        intentPhrases = listOf("convert", "how many", "in kilometers", "in miles", "in celsius", "in fahrenheit"),
        permissions = emptySet()
    )

    override fun canHandle(text: String): Boolean {
        val t = text.lowercase()
        return t.contains("convert") || (t.contains("how many") && hasUnit(t)) ||
            CONVERSIONS.keys.any { t.contains(it) }
    }

    private val CONVERSIONS = mapOf(
        "km to miles" to Pair("km", "miles"), "miles to km" to Pair("miles", "km"),
        "celsius to fahrenheit" to Pair("celsius", "fahrenheit"),
        "fahrenheit to celsius" to Pair("fahrenheit", "celsius"),
        "kg to pounds" to Pair("kg", "pounds"), "pounds to kg" to Pair("pounds", "kg"),
        "meters to feet" to Pair("meters", "feet"), "feet to meters" to Pair("feet", "meters")
    )

    private fun hasUnit(text: String) =
        listOf("km", "miles", "celsius", "fahrenheit", "kg", "pounds", "meters", "feet").any { text.contains(it) }

    override fun execute(text: String): SkillExecutionResult {
        val t = text.lowercase()
        val num = Regex("\\d+\\.?\\d*").find(t)?.value?.toDoubleOrNull()
            ?: return SkillExecutionResult(manifest.skillId, false, "I couldn't find a number to convert.")

        val result = when {
            "km" in t && "miles" in t && t.indexOf("km") < t.indexOf("miles") -> "${num * 0.621371} miles"
            "miles" in t && "km" in t && t.indexOf("miles") < t.indexOf("km") -> "${num * 1.60934} km"
            "celsius" in t && "fahrenheit" in t -> "${num * 9/5 + 32} °F"
            "fahrenheit" in t && "celsius" in t -> "${(num - 32) * 5/9} °C"
            "kg" in t && "pounds" in t -> "${num * 2.20462} pounds"
            "pounds" in t && "kg" in t -> "${num * 0.453592} kg"
            "meters" in t && "feet" in t -> "${num * 3.28084} feet"
            "feet" in t && "meters" in t -> "${num * 0.3048} meters"
            else -> return SkillExecutionResult(manifest.skillId, false, "I don't know how to convert that yet.")
        }
        return SkillExecutionResult(manifest.skillId, true, "$num converts to $result")
    }
}

class DeviceStatusSkill : BaseSkill() {
    override val manifest = SkillManifest(
        skillId = "nova.builtin.device_status",
        name = "Device Status",
        description = "Reports battery, storage, and device information",
        version = "1.0.0",
        author = "Nova First Party",
        category = SkillCategory.INFORMATION,
        isFirstParty = true,
        intentPhrases = listOf("device status", "battery status", "how much battery",
            "storage status", "phone info", "system info"),
        permissions = emptySet()
    )

    override fun canHandle(text: String): Boolean {
        val t = text.lowercase()
        return listOf("battery", "storage", "device status", "system info", "phone info").any { t.contains(it) }
    }

    override fun execute(text: String): SkillExecutionResult {
        val t = text.lowercase()
        val response = when {
            "battery" in t -> "Your battery level is reported from the system manager."
            "storage" in t -> "Device storage status is available through system settings."
            else -> "I'm Nova, running v3.0.0. All systems are operational."
        }
        return SkillExecutionResult(manifest.skillId, true, response)
    }
}

class NotesSkill : BaseSkill() {
    override val manifest = SkillManifest(
        skillId = "nova.builtin.notes",
        name = "Notes",
        description = "Take and recall quick notes",
        version = "1.0.0",
        author = "Nova First Party",
        category = SkillCategory.PRODUCTIVITY,
        isFirstParty = true,
        intentPhrases = listOf("take a note", "remember that", "note that", "what did i note", "read my notes"),
        permissions = setOf(SkillPermission.MEMORY_WRITE, SkillPermission.MEMORY_READ)
    )

    override fun canHandle(text: String): Boolean {
        val t = text.lowercase()
        return listOf("take a note", "remember that", "note that", "read my notes", "what did i note").any { t.contains(it) }
    }

    override fun execute(text: String): SkillExecutionResult {
        val t = text.lowercase()
        return when {
            "take a note" in t || "note that" in t || "remember that" in t -> {
                val noteText = text.replace(Regex("(?i)(take a note|note that|remember that):?"), "").trim()
                context.memoryApi?.remember("note_${System.currentTimeMillis()}", noteText)
                SkillExecutionResult(manifest.skillId, true, "Got it! I've noted: $noteText")
            }
            "read my notes" in t || "what did i note" in t -> {
                SkillExecutionResult(manifest.skillId, true, "Your notes are saved in memory.")
            }
            else -> SkillExecutionResult(manifest.skillId, false, "I didn't understand that note command.")
        }
    }
}

class TranslatorSkill : BaseSkill() {
    override val manifest = SkillManifest(
        skillId = "nova.builtin.translator",
        name = "Translator",
        description = "Translates phrases between languages (offline stub, online future)",
        version = "1.0.0",
        author = "Nova First Party",
        category = SkillCategory.INFORMATION,
        isFirstParty = true,
        intentPhrases = listOf("translate", "how do you say", "what is hello in", "say in"),
        permissions = emptySet()
    )

    override fun canHandle(text: String): Boolean {
        val t = text.lowercase()
        return listOf("translate", "how do you say", "what is hello in", "say in").any { t.contains(it) }
    }

    private val SAMPLES = mapOf(
        "hello" to mapOf("japanese" to "Konnichiwa", "spanish" to "Hola",
            "french" to "Bonjour", "german" to "Hallo", "hindi" to "Namaste"),
        "good morning" to mapOf("japanese" to "Ohayou Gozaimasu", "spanish" to "Buenos días",
            "french" to "Bonjour", "german" to "Guten Morgen", "hindi" to "Suprabhat"),
        "thank you" to mapOf("japanese" to "Arigatou", "spanish" to "Gracias",
            "french" to "Merci", "german" to "Danke", "hindi" to "Shukriya")
    )

    override fun execute(text: String): SkillExecutionResult {
        val t = text.lowercase()
        val lang = listOf("japanese", "spanish", "french", "german", "hindi").firstOrNull { t.contains(it) }
            ?: return SkillExecutionResult(manifest.skillId, false,
                "I currently support Japanese, Spanish, French, German, and Hindi translations offline.")

        val phrase = SAMPLES.entries.firstOrNull { (key, _) -> t.contains(key) }
        if (phrase == null) {
            return SkillExecutionResult(manifest.skillId, true,
                "Full translation requires an internet connection. Offline phrases are limited.")
        }
        val translation = phrase.value[lang]
            ?: return SkillExecutionResult(manifest.skillId, false, "I don't have that translation.")
        return SkillExecutionResult(manifest.skillId, true,
            "'${phrase.key.replaceFirstChar { it.uppercase() }}' in ${lang.replaceFirstChar { it.uppercase() }} is: $translation")
    }
}

class WeatherSkill : BaseSkill() {
    override val manifest = SkillManifest(
        skillId = "nova.builtin.weather",
        name = "Weather",
        description = "Provides weather information (requires internet connection)",
        version = "1.0.0",
        author = "Nova First Party",
        category = SkillCategory.INFORMATION,
        isFirstParty = true,
        intentPhrases = listOf("what's the weather", "weather today", "will it rain",
            "how hot is it", "temperature today", "what is the weather"),
        permissions = setOf(SkillPermission.NETWORK, SkillPermission.LOCATION)
    )

    override fun canHandle(text: String): Boolean {
        val t = text.lowercase()
        return listOf("weather", "rain today", "temperature", "will it rain", "how hot").any { t.contains(it) }
    }

    override fun execute(text: String): SkillExecutionResult {
        return SkillExecutionResult(manifest.skillId, true,
            "To check the weather, please enable location access and ensure you're connected to the internet. This feature connects to your configured weather provider.")
    }
}

class ReminderSkill : BaseSkill() {
    override val manifest = SkillManifest(
        skillId = "nova.builtin.reminder",
        name = "Reminder",
        description = "Sets reminders and reviews upcoming reminders",
        version = "1.0.0",
        author = "Nova First Party",
        category = SkillCategory.PRODUCTIVITY,
        isFirstParty = true,
        intentPhrases = listOf("remind me", "set a reminder", "don't let me forget", "what are my reminders"),
        permissions = setOf(SkillPermission.NOTIFICATIONS, SkillPermission.SCHEDULER)
    )

    override fun canHandle(text: String): Boolean {
        val t = text.lowercase()
        return listOf("remind me", "set a reminder", "don't let me forget", "what are my reminders").any { t.contains(it) }
    }

    override fun execute(text: String): SkillExecutionResult {
        val t = text.lowercase()
        return if ("what are my reminders" in t) {
            SkillExecutionResult(manifest.skillId, true, "Your reminders are managed through Nova's scheduler.")
        } else {
            val content = text.replace(Regex("(?i)(remind me (to)?|set a reminder (to)?|don.t let me forget (to)?)"), "").trim()
            context.notificationApi?.notify("Reminder Set", "Nova will remind you: $content")
            SkillExecutionResult(manifest.skillId, true, "Done! I'll remind you: $content")
        }
    }
}

class AlarmSkill : BaseSkill() {
    override val manifest = SkillManifest(
        skillId = "nova.builtin.alarm",
        name = "Alarm",
        description = "Sets and manages alarms",
        version = "1.0.0",
        author = "Nova First Party",
        category = SkillCategory.UTILITIES,
        isFirstParty = true,
        intentPhrases = listOf("set an alarm", "wake me up at", "alarm for", "cancel alarm"),
        permissions = setOf(SkillPermission.NOTIFICATIONS)
    )

    override fun canHandle(text: String): Boolean {
        val t = text.lowercase()
        return listOf("set an alarm", "wake me up at", "alarm for", "cancel alarm").any { t.contains(it) }
    }

    override fun execute(text: String): SkillExecutionResult {
        val time = Regex("\\d{1,2}:\\d{2}|\\d{1,2} (am|pm)", RegexOption.IGNORE_CASE).find(text)?.value
        return if (time != null) {
            SkillExecutionResult(manifest.skillId, true, "Alarm set for $time.")
        } else {
            SkillExecutionResult(manifest.skillId, false, "What time should I set the alarm for?")
        }
    }
}

class TimerSkill : BaseSkill() {
    override val manifest = SkillManifest(
        skillId = "nova.builtin.timer",
        name = "Timer",
        description = "Sets countdown timers",
        version = "1.0.0",
        author = "Nova First Party",
        category = SkillCategory.UTILITIES,
        isFirstParty = true,
        intentPhrases = listOf("set a timer", "start a timer", "timer for", "stop the timer"),
        permissions = setOf(SkillPermission.NOTIFICATIONS)
    )

    override fun canHandle(text: String): Boolean {
        val t = text.lowercase()
        return listOf("set a timer", "start a timer", "timer for", "stop the timer").any { t.contains(it) }
    }

    override fun execute(text: String): SkillExecutionResult {
        val t = text.lowercase()
        val mins = Regex("(\\d+)\\s*minute").find(t)?.groupValues?.get(1)
        val secs = Regex("(\\d+)\\s*second").find(t)?.groupValues?.get(1)
        return when {
            mins != null -> SkillExecutionResult(manifest.skillId, true, "Timer set for $mins minutes.")
            secs != null -> SkillExecutionResult(manifest.skillId, true, "Timer set for $secs seconds.")
            "stop" in t -> SkillExecutionResult(manifest.skillId, true, "Timer stopped.")
            else -> SkillExecutionResult(manifest.skillId, false, "How long should the timer be?")
        }
    }
}
