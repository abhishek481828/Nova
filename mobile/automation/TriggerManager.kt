package com.nova.mobile.automation

import android.util.Log

/**
 * TriggerManager — Evaluates incoming events against all enabled routines.
 * When a trigger matches, it signals AutomationManager to execute the routine.
 * Voice triggers are matched against trigger.voicePhrase.
 */
class TriggerManager(private val repository: AutomationRepository) {
    companion object { private const val TAG = "TriggerManager" }

    private val listeners = mutableListOf<(Routine) -> Unit>()

    // ── System events fired by Android receivers ──────────────────────────────

    fun onVoiceCommand(spokenText: String) {
        val text = spokenText.lowercase().trim()
        val matched = repository.getEnabled().filter { routine ->
            routine.trigger.type == TriggerType.VOICE_COMMAND &&
            routine.trigger.voicePhrase?.lowercase()?.let { text.contains(it) } == true
        }
        matched.forEach { fire(it, "VOICE: $spokenText") }
    }

    fun onScreenOn() = fireByType(TriggerType.SCREEN_ON, "SCREEN_ON")
    fun onScreenOff() = fireByType(TriggerType.SCREEN_OFF, "SCREEN_OFF")
    fun onBluetoothConnected(device: String) {
        repository.getEnabled().filter { r ->
            r.trigger.type == TriggerType.BLUETOOTH_CONNECTED &&
            (r.trigger.bluetoothDevice == null || r.trigger.bluetoothDevice == device)
        }.forEach { fire(it, "BT:$device") }
    }
    fun onWifiConnected(ssid: String) {
        repository.getEnabled().filter { r ->
            r.trigger.type == TriggerType.WIFI_CONNECTED &&
            (r.trigger.wifiSsid == null || r.trigger.wifiSsid == ssid)
        }.forEach { fire(it, "WIFI:$ssid") }
    }
    fun onBatteryCharging() = fireByType(TriggerType.BATTERY_CHARGING, "CHARGING")
    fun onHeadphonesConnected() = fireByType(TriggerType.HEADPHONES_CONNECTED, "HEADPHONES")
    fun onNovaCoreConnected() = fireByType(TriggerType.NOVA_CORE_CONNECTED, "CORE_CONNECTED")
    fun onNovaCoreDisconnected() = fireByType(TriggerType.NOVA_CORE_DISCONNECTED, "CORE_DISCONNECTED")

    /** Called by AutomationScheduler at HH:MM ticks */
    fun onTimeTick(hour: Int, minute: Int) {
        repository.getEnabled().filter { r ->
            r.trigger.type == TriggerType.TIME &&
            r.trigger.timeHour == hour &&
            r.trigger.timeMinute == minute
        }.forEach { fire(it, "TIME:$hour:$minute") }
    }

    /** Manual trigger by routine ID */
    fun triggerManual(routineId: String): Boolean {
        val routine = repository.get(routineId) ?: return false
        if (routine.status != AutomationStatus.ENABLED) return false
        fire(routine, "MANUAL")
        return true
    }

    fun addListener(listener: (Routine) -> Unit) { listeners.add(listener) }

    private fun fireByType(type: TriggerType, source: String) {
        repository.getEnabled()
            .filter { it.trigger.type == type }
            .forEach { fire(it, source) }
    }

    private fun fire(routine: Routine, source: String) {
        Log.i(TAG, "Trigger fired: '${routine.name}' from $source")
        listeners.forEach { it(routine) }
    }
}
