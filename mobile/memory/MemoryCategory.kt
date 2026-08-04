package com.nova.mobile.memory

enum class MemoryCategory(val label: String) {
    FAVORITE_CONTACT("Favorite Contacts"),
    FAVORITE_APP("Favorite Applications"),
    PREFERRED_MUSIC_APP("Preferred Music App"),
    PREFERRED_BROWSER("Preferred Browser"),
    PREFERRED_MAPS_APP("Preferred Maps App"),
    PREFERRED_CAMERA_MODE("Preferred Camera Mode"),
    PREFERRED_BRIGHTNESS("Preferred Brightness"),
    PREFERRED_VOLUME("Preferred Volume"),
    PREFERRED_LANGUAGE("Preferred Language"),
    FREQUENT_COMMAND("Frequently Used Commands"),
    RECENT_COMMAND("Recent Commands"),
    TRUSTED_DEVICE("Trusted Devices"),
    KNOWN_WIFI("Known Wi-Fi Networks"),
    DAILY_ROUTINE("Daily Routines"),
    REMINDER_PREFERENCE("Reminder Preferences"),
    CALENDAR_PREFERENCE("Calendar Preferences"),
    USER_PREFERENCE("User Preferences")
}

enum class MemoryEvent {
    MEMORY_CREATED,
    MEMORY_UPDATED,
    MEMORY_DELETED,
    MEMORY_SYNCHRONIZED,
    MEMORY_IMPORT_COMPLETED,
    MEMORY_EXPORT_COMPLETED,
    MEMORY_CLEARED
}
