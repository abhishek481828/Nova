package com.nova.companion.event

import android.util.Log
import org.json.JSONObject
import java.util.concurrent.CopyOnWriteArrayList

object EventBus {
    private const val TAG = "EventBus"
    private val listeners = CopyOnWriteArrayList<(eventName: String, data: JSONObject) -> Unit>()

    fun subscribe(listener: (eventName: String, data: JSONObject) -> Unit) {
        listeners.add(listener)
    }

    fun unsubscribe(listener: (eventName: String, data: JSONObject) -> Unit) {
        listeners.remove(listener)
    }

    fun publish(eventName: String, data: JSONObject = JSONObject()) {
        Log.i(TAG, "Publishing event '$eventName': $data")
        for (listener in listeners) {
            try {
                listener.invoke(eventName, data)
            } catch (e: Exception) {
                Log.e(TAG, "Error notifying EventBus listener for '$eventName'", e)
            }
        }
    }
}
