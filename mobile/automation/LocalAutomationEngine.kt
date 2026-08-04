package com.nova.mobile.automation

/**
 * LocalAutomationEngine — Public facade for Phase 7 automation system.
 * Delegates to AutomationManager. Retained for backward compatibility.
 */
class LocalAutomationEngine(val manager: AutomationManager) {
    fun getRulesCount(): Int = manager.repository.count()
    fun getEnabledCount(): Int = manager.repository.countEnabled()
    fun getHistory(): AutomationHistory = manager.history
}
