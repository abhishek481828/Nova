package com.nova.mobile.lifecycle

import android.content.Context
import android.util.Log

data class LifecycleEvent(
    val eventName: String,
    val payload: Map<String, Any> = emptyMap(),
    val timestamp: Long = System.currentTimeMillis()
)

typealias LifecycleListener = (LifecycleEvent) -> Unit

class LifecycleManager(private val context: Context) {
    companion object {
        private const val TAG = "LifecycleManager"
    }

    private val listeners = mutableListOf<LifecycleListener>()
    private val eventHistory = mutableListOf<LifecycleEvent>()

    fun initialize() {
        Log.i(TAG, "Initializing LifecycleManager...")
    }

    fun subscribe(listener: LifecycleListener) {
        listeners.add(listener)
    }

    fun unsubscribe(listener: LifecycleListener) {
        listeners.remove(listener)
    }

    fun publishEvent(eventName: String, payload: Map<String, Any> = emptyMap()) {
        val event = LifecycleEvent(eventName, payload)
        eventHistory.add(event)
        Log.i(TAG, "Lifecycle Event: $eventName -> $payload")

        for (listener in listeners) {
            try {
                listener(event)
            } catch (e: Exception) {
                Log.e(TAG, "Error in lifecycle listener for event $eventName", e)
            }
        }
    }

    fun getEventHistory(): List<LifecycleEvent> = eventHistory.toList()
}
