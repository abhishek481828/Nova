package com.nova.mobile.wakeword

data class WakeWordMetrics(
    var totalDetections: Int = 0,
    var lastDetectionTimestamp: Long = 0L,
    var falsePositives: Int = 0,
    var totalRecoveryAttempts: Int = 0,
    var averageProcessingMs: Double = 0.0,
    var cpuUsagePercent: Float = 1.2f,
    var batteryImpactLevel: String = "LOW"
) {
    fun recordDetection() {
        totalDetections++
        lastDetectionTimestamp = System.currentTimeMillis()
    }

    fun recordRecovery() {
        totalRecoveryAttempts++
    }
}
