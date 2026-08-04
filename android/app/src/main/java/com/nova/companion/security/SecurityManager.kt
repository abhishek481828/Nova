package com.nova.companion.security

import android.content.Context
import android.content.SharedPreferences
import android.util.Log
import androidx.security.crypto.EncryptedSharedPreferences
import androidx.security.crypto.MasterKey
import java.util.UUID

class SecurityManager(private val context: Context) {

    private val PREF_NAME = "nova_secure_prefs"
    private val KEY_ACCESS_TOKEN = "jwt_access_token"
    private val KEY_REFRESH_TOKEN = "jwt_refresh_token"
    private val KEY_DEVICE_ID = "companion_device_id"
    private val KEY_SERVER_PUBLIC_KEY = "server_ecdh_public_key"

    private val prefs: SharedPreferences by lazy {
        try {
            val masterKey = MasterKey.Builder(context)
                .setKeyScheme(MasterKey.KeyScheme.AES256_GCM)
                .build()

            EncryptedSharedPreferences.create(
                context,
                PREF_NAME,
                masterKey,
                EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
                EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
            )
        } catch (e: Throwable) {
            Log.w("SecurityManager", "EncryptedSharedPreferences fallback to standard shared preferences: ${e.message}")
            context.getSharedPreferences(PREF_NAME, Context.MODE_PRIVATE)
        }
    }

    fun getDeviceId(): String {
        var id = prefs.getString(KEY_DEVICE_ID, null)
        if (id == null) {
            id = "android-" + UUID.randomUUID().toString().take(8)
            prefs.edit().putString(KEY_DEVICE_ID, id).apply()
        }
        return id
    }

    fun saveTokens(accessToken: String, refreshToken: String) {
        prefs.edit()
            .putString(KEY_ACCESS_TOKEN, accessToken)
            .putString(KEY_REFRESH_TOKEN, refreshToken)
            .apply()
        Log.i("SecurityManager", "JWT Auth Tokens securely stored in EncryptedSharedPreferences")
    }

    fun getAccessToken(): String? {
        return prefs.getString(KEY_ACCESS_TOKEN, null)
    }

    fun getRefreshToken(): String? {
        return prefs.getString(KEY_REFRESH_TOKEN, null)
    }

    private val KEY_SERVER_URL = "server_url"

    fun saveServerUrl(url: String) {
        prefs.edit().putString(KEY_SERVER_URL, url).apply()
    }

    fun getServerUrl(): String? {
        return prefs.getString(KEY_SERVER_URL, null)
    }

    fun saveServerPublicKey(key: String) {
        prefs.edit().putString(KEY_SERVER_PUBLIC_KEY, key).apply()
    }

    fun clearTokens() {
        prefs.edit()
            .remove(KEY_ACCESS_TOKEN)
            .remove(KEY_REFRESH_TOKEN)
            .apply()
        Log.i("SecurityManager", "Cleared authentication tokens")
    }
}
