package com.nova.mobile.command

import android.util.Log

class ExecutionContext {
    companion object {
        private const val TAG = "ExecutionContext"
        private const val CONTEXT_TTL_MS = 60000L // 60 seconds TTL
    }

    var lastContact: String? = null
        private set
    var lastApp: String? = null
        private set
    var lastTimestamp: Long = 0L
        private set

    fun updateContext(contact: String? = null, app: String? = null) {
        if (!contact.isNull_or_empty_custom()) lastContact = contact
        if (!app.isNull_or_empty_custom()) lastApp = app
        lastTimestamp = System.currentTimeMillis()
        Log.i(TAG, "Updated Context: lastContact=$lastContact, lastApp=$lastApp")
    }

    fun resolveContact(pronounOrName: String): String {
        val clean = pronounOrName.trim().lowercase()
        if (clean in listOf("him", "her", "them", "he", "she") && isContextValid()) {
            return lastContact ?: pronounOrName
        }
        return pronounOrName
    }

    fun isContextValid(): Boolean {
        return (System.currentTimeMillis() - lastTimestamp) <= CONTEXT_TTL_MS
    }

    fun clear() {
        lastContact = null
        lastApp = null
        lastTimestamp = 0L
    }

    private fun String?.isNull_or_empty_custom(): Boolean = this == null || this.trim().isEmpty()
}
