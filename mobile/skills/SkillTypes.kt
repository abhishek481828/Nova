package com.nova.mobile.skills

enum class SkillPermission(val label: String, val requiresUserApproval: Boolean) {
    CAMERA("Camera", true),
    CONTACTS("Contacts", true),
    SMS("Send SMS", true),
    LOCATION("Location", true),
    MICROPHONE("Microphone", true),
    NOTIFICATIONS("Notifications", false),
    STORAGE("Storage", false),
    ACCESSIBILITY("Accessibility Service", true),
    NETWORK("Network", false),
    NOVA_CORE("Nova Core Communication", false),
    MEMORY_READ("Read Nova Memory", false),
    MEMORY_WRITE("Write Nova Memory", false),
    AUTOMATION("Automation Access", false),
    SCHEDULER("Scheduler Access", false)
}

enum class SkillStatus {
    NOT_INSTALLED,
    INSTALLED,
    LOADING,
    LOADED,
    RUNNING,
    DISABLED,
    ERROR,
    UPDATING,
    UNLOADING
}

enum class SkillCategory {
    PRODUCTIVITY,
    COMMUNICATION,
    ENTERTAINMENT,
    UTILITIES,
    INFORMATION,
    HOME_AUTOMATION,
    HEALTH,
    NAVIGATION,
    EDUCATION,
    FINANCE,
    CUSTOM
}

enum class SkillLifecycleEvent {
    INSTALLED,
    LOADED,
    ENABLED,
    DISABLED,
    UNLOADED,
    REMOVED,
    UPDATED,
    ERROR,
    PERMISSION_GRANTED,
    PERMISSION_DENIED
}
