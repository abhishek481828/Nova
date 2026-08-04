package com.nova.mobile.command

import java.util.regex.Pattern

class EntityExtractor {

    fun extract(text: String, intent: BuiltInIntent, context: ExecutionContext): Map<String, String> {
        val entities = mutableMapOf<String, String>()
        val clean = text.trim()

        when (intent) {
            BuiltInIntent.CALL_CONTACT -> {
                val name = parseTargetName(clean, listOf("call", "phone", "dial"))
                val resolved = context.resolveContact(name)
                if (resolved.isNotBlank()) {
                    entities["contact"] = resolved
                    context.updateContext(contact = resolved)
                }
            }

            BuiltInIntent.SEND_SMS -> {
                val name = parseTargetName(clean, listOf("send sms to", "send message to", "text", "msg"))
                val resolved = context.resolveContact(name)
                if (resolved.isNotBlank()) {
                    entities["contact"] = resolved
                    context.updateContext(contact = resolved)
                }
                val msgContent = parseMessageBody(clean)
                if (msgContent.isNotBlank()) {
                    entities["message"] = msgContent
                }
            }

            BuiltInIntent.OPEN_APP -> {
                val app = parseAppName(clean)
                if (app.isNotBlank()) {
                    entities["app"] = app
                    context.updateContext(app = app)
                }
            }

            BuiltInIntent.PLAY_YOUTUBE, BuiltInIntent.PLAY_SPOTIFY -> {
                val query = parseMediaQuery(clean)
                if (query.isNotBlank()) {
                    entities["query"] = query
                }
            }

            BuiltInIntent.SET_VOLUME, BuiltInIntent.SET_BRIGHTNESS -> {
                val percent = parsePercentage(clean)
                if (percent >= 0) {
                    entities["percentage"] = percent.toString()
                }
            }

            BuiltInIntent.SEARCH_GOOGLE -> {
                val query = clean.replace(Regex("(?i)^(search|search google for|google)"), "").trim()
                if (query.isNotBlank()) entities["query"] = query
            }

            BuiltInIntent.OPEN_MAPS -> {
                val dest = clean.replace(Regex("(?i)^(navigate to|maps to|open maps)"), "").trim()
                if (dest.isNotBlank()) entities["destination"] = dest
            }

            else -> {}
        }

        return entities
    }

    private fun parseTargetName(text: String, prefixes: List<String>): String {
        var result = text
        for (prefix in prefixes) {
            val pattern = Pattern.compile("(?i)^" + Pattern.quote(prefix) + "\\s+")
            val matcher = pattern.matcher(result)
            if (matcher.find()) {
                result = matcher.replaceFirst("")
                break
            }
        }
        return result.replace(Regex("(?i)\\s+(on whatsapp|on phone|app)$"), "").trim()
    }

    private fun parseAppName(text: String): String {
        return text.replace(Regex("(?i)^(open|launch|start)\\s+"), "")
            .replace(Regex("(?i)\\s+(on phone|app)$"), "").trim()
    }

    private fun parseMediaQuery(text: String): String {
        return text.replace(Regex("(?i)^(play|play music|play song)\\s+"), "")
            .replace(Regex("(?i)\\s+(on youtube|on spotify|app)$"), "").trim()
    }

    private fun parsePercentage(text: String): Int {
        val p = Pattern.compile("(\\d{1,3})\\s*%?")
        val m = p.matcher(text)
        if (m.find()) {
            val valInt = m.group(1)?.toIntOrNull() ?: -1
            if (valInt in 0..100) return valInt
        }
        return -1
    }

    private fun parseMessageBody(text: String): String {
        val p = Pattern.compile("(?i)message\\s+(?:that|saying)?\\s+(.*)")
        val m = p.matcher(text)
        if (m.find()) {
            return m.group(1)?.trim() ?: ""
        }
        return ""
    }
}
