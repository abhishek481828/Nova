package com.nova.mobile.hybrid

enum class ExecutionTarget {
    LOCAL_ANDROID,
    NOVA_CORE,
    CLOUD_FUTURE,
    UNKNOWN
}

enum class RoutingPolicy {
    AUTOMATIC,
    ALWAYS_LOCAL,
    ALWAYS_NOVA_CORE,
    FALLBACK,
    OFFLINE_MODE
}
