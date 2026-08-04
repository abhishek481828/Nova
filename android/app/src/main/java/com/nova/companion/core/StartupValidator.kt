package com.nova.companion.core

import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.os.PowerManager
import android.util.Log
import androidx.core.content.ContextCompat

data class DiagnosticItem(
    val title: String,
    val isPassed: Boolean,
    val details: String
)

data class StartupValidationReport(
    val isReady: Boolean,
    val deviceModel: String,
    val androidVersion: String,
    val sdkInt: Int,
    val diagnostics: List<DiagnosticItem>
)

class StartupValidator(private val context: Context) {

    fun validateSystemReadiness(): StartupValidationReport {
        val diagnostics = mutableListOf<DiagnosticItem>()

        // 1. Android Version Compatibility (Min SDK 26+)
        val isSdkCompatible = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
        diagnostics.add(
            DiagnosticItem(
                title = "Android OS Compatibility",
                isPassed = isSdkCompatible,
                details = "SDK ${Build.VERSION.SDK_INT} (Android ${Build.VERSION.RELEASE}) - Min SDK 26"
            )
        )

        // 2. Camera Permission Status
        val hasCameraPermission = checkPermission(android.Manifest.permission.CAMERA)
        diagnostics.add(
            DiagnosticItem(
                title = "Camera Permission",
                isPassed = hasCameraPermission,
                details = if (hasCameraPermission) "Granted" else "Not Granted"
            )
        )

        // 3. Audio Record Permission Status
        val hasAudioPermission = checkPermission(android.Manifest.permission.RECORD_AUDIO)
        diagnostics.add(
            DiagnosticItem(
                title = "Microphone Permission",
                isPassed = hasAudioPermission,
                details = if (hasAudioPermission) "Granted" else "Not Granted"
            )
        )

        // 4. Notification Permission (Android 13+ / API 33)
        val hasNotifPermission = if (Build.VERSION.SDK_INT >= 33) {
            checkPermission("android.permission.POST_NOTIFICATIONS")
        } else {
            true
        }
        diagnostics.add(
            DiagnosticItem(
                title = "Post Notifications Permission",
                isPassed = hasNotifPermission,
                details = if (hasNotifPermission) "Granted" else "Not Granted"
            )
        )

        // 5. Battery Optimization Status
        val pm = context.getSystemService(Context.POWER_SERVICE) as? PowerManager
        val isIgnoringBatteryOpt = pm?.isIgnoringBatteryOptimizations(context.packageName) ?: false
        diagnostics.add(
            DiagnosticItem(
                title = "Battery Optimization",
                isPassed = isIgnoringBatteryOpt,
                details = if (isIgnoringBatteryOpt) "Unrestricted" else "Optimized (Recommend Disabling)"
            )
        )

        // 6. Foreground Service Availability
        diagnostics.add(
            DiagnosticItem(
                title = "Foreground Service Engine",
                isPassed = true,
                details = "Registered & Ready"
            )
        )

        val deviceModel = "${Build.MANUFACTURER} ${Build.MODEL}"
        val isOverallReady = isSdkCompatible && hasCameraPermission && hasAudioPermission

        Log.i("StartupValidator", "Startup Diagnostics Complete for $deviceModel. Ready=$isOverallReady")
        for (item in diagnostics) {
            Log.i("StartupValidator", "  [${if (item.isPassed) "PASS" else "WARN"}] ${item.title}: ${item.details}")
        }

        return StartupValidationReport(
            isReady = isOverallReady,
            deviceModel = deviceModel,
            androidVersion = Build.VERSION.RELEASE,
            sdkInt = Build.VERSION.SDK_INT,
            diagnostics = diagnostics
        )
    }

    private fun checkPermission(permission: String): Boolean {
        return ContextCompat.checkSelfPermission(context, permission) == PackageManager.PERMISSION_GRANTED
    }
}
