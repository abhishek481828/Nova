package com.nova.companion.plugins.communication

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.provider.ContactsContract
import android.util.Log
import androidx.core.content.ContextCompat
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONArray
import org.json.JSONObject

class ContactsHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "communication.contacts"
    override val supportedActions: List<String> = listOf(
        "contacts.list",
        "contacts.search",
        "contacts.details"
    )

    override fun execute(action: String, payload: JSONObject): ActionResult {
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            return ActionResult("error", error = "Permission READ_CONTACTS is not granted", errorCode = "MISSING_PERMISSIONS")
        }

        val query = payload.optString("query", "").trim()
        val limit = payload.optInt("limit", 50)

        return searchContacts(query, limit)
    }

    private fun searchContacts(query: String, limit: Int): ActionResult {
        val contactsList = JSONArray()
        try {
            val selection = if (query.isNotEmpty()) {
                "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} LIKE ? OR ${ContactsContract.CommonDataKinds.Phone.NUMBER} LIKE ?"
            } else null

            val selectionArgs = if (query.isNotEmpty()) {
                arrayOf("%$query%", "%$query%")
            } else null

            val cursor = context.contentResolver.query(
                ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                arrayOf(
                    ContactsContract.CommonDataKinds.Phone.CONTACT_ID,
                    ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
                    ContactsContract.CommonDataKinds.Phone.NUMBER
                ),
                selection,
                selectionArgs,
                "${ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME} ASC"
            )

            cursor?.use {
                val idIdx = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.CONTACT_ID)
                val nameIdx = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME)
                val numIdx = it.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER)

                var count = 0
                while (it.moveToNext() && count < limit) {
                    val contact = JSONObject().apply {
                        put("contact_id", if (idIdx >= 0) it.getString(idIdx) else "")
                        put("name", if (nameIdx >= 0) it.getString(nameIdx) else "Unknown")
                        put("number", if (numIdx >= 0) it.getString(numIdx) else "")
                    }
                    contactsList.put(contact)
                    count++
                }
            }

            Log.i("ContactsHandler", "Retrieved ${contactsList.length()} contacts matching query: '$query'")
            return ActionResult("success", data = JSONObject().apply { put("contacts", contactsList) })

        } catch (e: Exception) {
            Log.e("ContactsHandler", "Failed to query contacts: ${e.message}")
            return ActionResult("error", error = e.message ?: "Failed to query ContactsProvider", errorCode = "CONTACTS_READ_FAILURE")
        }
    }
}
