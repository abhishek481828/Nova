package com.nova.mobile.command

data class CommandResult(
    val commandId: String,
    val intent: BuiltInIntent,
    val isSuccess: Boolean,
    val spokenResponse: String,
    val pluginUsed: String,
    val entities: Map<String, String> = emptyMap(),
    val executionTimeMs: Long = 0L,
    val errorMessage: String? = null
)
