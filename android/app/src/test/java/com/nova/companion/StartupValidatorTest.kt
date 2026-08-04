package com.nova.companion

import com.nova.companion.core.DiagnosticItem
import com.nova.companion.core.StartupValidationReport
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class StartupValidatorTest {

    @Test
    fun testStartupValidationReportModel() {
        val diagnostics = listOf(
            DiagnosticItem("Android OS Compatibility", true, "SDK 31 (Android 12)"),
            DiagnosticItem("Camera Permission", true, "Granted"),
            DiagnosticItem("Microphone Permission", true, "Granted"),
            DiagnosticItem("Foreground Service Engine", true, "Registered & Ready")
        )

        val report = StartupValidationReport(
            isReady = true,
            deviceModel = "samsung SM-A135F",
            androidVersion = "12",
            sdkInt = 31,
            diagnostics = diagnostics
        )

        assertTrue(report.isReady)
        assertEquals("samsung SM-A135F", report.deviceModel)
        assertEquals("12", report.androidVersion)
        assertEquals(31, report.sdkInt)
        assertEquals(4, report.diagnostics.size)
    }

    @Test
    fun testDiagnosticItemPassedState() {
        val item = DiagnosticItem("Foreground Service Engine", true, "Registered & Ready")
        assertTrue(item.isPassed)
        assertEquals("Foreground Service Engine", item.title)
    }
}
