package com.nova.mobile.services

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import com.nova.mobile.core.MobileCoreManager

/**
 * Nova v3.0 — Nova Mobile Permanent Foreground Service
 * Keeps Nova Mobile alive, monitors service lifecycle, battery optimization, and network state.
 */
class NovaMobileForegroundService : Service() {

    companion object {
        private const val TAG = "NovaMobileService"
        private const val NOTIFICATION_ID = 3001
        private const val CHANNEL_ID = "nova_mobile_service_channel"

        fun startService(context: Context) {
            val intent = Intent(context, NovaMobileForegroundService::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(intent)
            } else {
                context.startService(intent)
            }
        }

        fun stopService(context: Context) {
            val intent = Intent(context, NovaMobileForegroundService::class.java)
            context.stopService(intent)
        }
    }

    private var isServiceRunning = false

    override fun onCreate() {
        super.onCreate()
        Log.i(TAG, "NovaMobileForegroundService onCreate")
        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        Log.i(TAG, "NovaMobileForegroundService onStartCommand")
        startForeground(NOTIFICATION_ID, createNotification())
        isServiceRunning = true

        // Initialize Mobile Core Manager
        val coreManager = MobileCoreManager.getInstance(this)
        if (!coreManager.isInitialized) {
            coreManager.initialize()
        }

        return START_STICKY
    }

    override fun onDestroy() {
        super.onDestroy()
        Log.i(TAG, "NovaMobileForegroundService onDestroy")
        isServiceRunning = false
        MobileCoreManager.getInstance(this).shutdown()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Nova Mobile Foundation Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps Nova Mobile Foundation active in background"
            }
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(channel)
        }
    }

    private fun createNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Nova Mobile v3.0")
            .setContentText("Nova Mobile Foundation Active")
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }
}
