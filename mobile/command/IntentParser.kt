package com.nova.mobile.command

class IntentParser {

    fun parse(text: String): BuiltInIntent {
        val clean = text.trim().lowercase()

        return when {
            // Flashlight
            clean.contains("turn on flashlight") || clean.contains("flashlight on") || clean.contains("torch on") -> BuiltInIntent.FLASHLIGHT_ON
            clean.contains("turn off flashlight") || clean.contains("flashlight off") || clean.contains("torch off") -> BuiltInIntent.FLASHLIGHT_OFF

            // Calls & Messages
            clean.startsWith("call ") || clean.startsWith("phone ") || clean.startsWith("dial ") -> BuiltInIntent.CALL_CONTACT
            clean.startsWith("send sms") || clean.startsWith("send message") || clean.startsWith("text ") -> BuiltInIntent.SEND_SMS

            // App Launches & Media
            clean.startsWith("play ") && (clean.contains("youtube") || clean.contains("video")) -> BuiltInIntent.PLAY_YOUTUBE
            clean.startsWith("play ") && clean.contains("spotify") -> BuiltInIntent.PLAY_SPOTIFY
            clean.startsWith("play ") || clean == "play music" -> BuiltInIntent.PLAY_YOUTUBE

            clean.startsWith("open youtube") -> BuiltInIntent.PLAY_YOUTUBE
            clean.startsWith("open camera") || clean.startsWith("launch camera") -> BuiltInIntent.OPEN_CAMERA
            clean.startsWith("take a photo") || clean.startsWith("take photo") || clean.startsWith("snap picture") -> BuiltInIntent.TAKE_PHOTO
            clean.startsWith("open chrome") || clean.startsWith("open browser") -> BuiltInIntent.OPEN_BROWSER
            clean.startsWith("open maps") || clean.startsWith("navigate to") -> BuiltInIntent.OPEN_MAPS
            clean.startsWith("open settings") -> BuiltInIntent.OPEN_SETTINGS
            clean.startsWith("open gallery") || clean.startsWith("open photos") -> BuiltInIntent.OPEN_GALLERY
            clean.startsWith("open ") || clean.startsWith("launch ") -> BuiltInIntent.OPEN_APP

            // Device Adjustments
            clean.contains("volume") -> BuiltInIntent.SET_VOLUME
            clean.contains("brightness") -> BuiltInIntent.SET_BRIGHTNESS

            // Alarms & Timers & Search
            clean.contains("alarm") -> BuiltInIntent.SET_ALARM
            clean.contains("timer") -> BuiltInIntent.SET_TIMER
            clean.startsWith("search ") || clean.startsWith("google ") -> BuiltInIntent.SEARCH_GOOGLE

            // Status & Notifications
            clean.contains("notification") -> BuiltInIntent.SHOW_NOTIFICATIONS
            clean.contains("battery") -> BuiltInIntent.BATTERY_STATUS
            clean.contains("device status") || clean.contains("phone status") -> BuiltInIntent.DEVICE_STATUS

            else -> BuiltInIntent.UNKNOWN
        }
    }
}
