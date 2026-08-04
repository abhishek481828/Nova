package com.nova.mobile.hybrid

data class ExecutionResult(
    val requestId: String,
    val intent: String,
    val target: ExecutionTarget,
    val isSuccess: Boolean,
    val spokenResponse: String,
    val executionTimeMs: Long = 0L,
    val networkLatencyMs: Long = 0L,
    val errorMessage: String? = null,
    val usedFallback: Boolean = false
)
