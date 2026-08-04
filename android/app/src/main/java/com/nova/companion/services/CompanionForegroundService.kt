package com.nova.companion.services

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
import com.nova.companion.R
import com.nova.companion.plugins.ActionRegistry
import com.nova.companion.plugins.hardware.*
import com.nova.companion.plugins.media.CameraHandler
import com.nova.companion.plugins.media.GalleryHandler
import com.nova.companion.plugins.media.ScreenHandler
import com.nova.companion.plugins.system.AppLauncherHandler
import com.nova.companion.plugins.system.ClipboardHandler
import com.nova.companion.plugins.system.NotificationHandler
import com.nova.companion.plugins.communication.SMSHandler
import com.nova.companion.plugins.communication.ContactsHandler
import com.nova.companion.plugins.communication.CallHandler
import com.nova.companion.security.SecurityManager
import com.nova.companion.transport.WebSocketClientManager

import com.nova.companion.plugins.accessibility.AccessibilityHandler
import com.nova.companion.plugins.app.AppControlHandler
import com.nova.companion.plugins.audio.AudioHandler
import com.nova.companion.plugins.device.DeviceManagementHandler
import com.nova.companion.plugins.file.FileManagerHandler

class CompanionForegroundService : Service() {

    private val CHANNEL_ID = "nova_companion_service_channel"
    private val NOTIFICATION_ID = 2001

    private val actionRegistry = ActionRegistry()
    private lateinit var wsClient: WebSocketClientManager
    private lateinit var securityManager: SecurityManager
    private lateinit var deviceInfoHandler: DeviceInfoHandler

    override fun onCreate() {
        super.onCreate()
        Log.i("ForegroundService", "Initializing Nova Companion Foreground Service...")

        // Feature Plugin Registrations (Steps 2 - 8)
        deviceInfoHandler = DeviceInfoHandler(this)
        actionRegistry.register(deviceInfoHandler)
        actionRegistry.register(FlashlightHandler(this))
        actionRegistry.register(VolumeHandler(this))
        actionRegistry.register(VibrationHandler(this))
        actionRegistry.register(RingtoneHandler(this))
        actionRegistry.register(ClipboardHandler(this))
        actionRegistry.register(NotificationHandler())
        actionRegistry.register(CameraHandler(this))
        actionRegistry.register(GalleryHandler(this))
        actionRegistry.register(AccessibilityHandler(this))
        actionRegistry.register(AppControlHandler(this))
        actionRegistry.register(ScreenHandler(this))
        actionRegistry.register(AudioHandler(this))
        actionRegistry.register(SMSHandler(this))
        actionRegistry.register(ContactsHandler(this))
        actionRegistry.register(CallHandler(this))
        actionRegistry.register(DeviceManagementHandler(this))
        actionRegistry.register(FileManagerHandler(this))

        securityManager = SecurityManager(this)
        wsClient = WebSocketClientManager(actionRegistry, deviceInfoHandler)

        createNotificationChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(
                NOTIFICATION_ID,
                notification,
                android.content.pm.ServiceInfo.FOREGROUND_SERVICE_TYPE_CONNECTED_DEVICE
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }

        val token = securityManager.getAccessToken()
        val deviceId = securityManager.getDeviceId()
        val serverUrl = intent?.getStringExtra("server_url")
            ?: securityManager.getServerUrl()
            ?: "ws://10.0.2.2:8000/api/v2/companion/ws"

        if (token != null && deviceId != null) {
            wsClient.connect(serverUrl, token, deviceId)
        } else {
            Log.w("ForegroundService", "No saved auth tokens found. Awaiting user pairing in app UI.")
        }

        return START_STICKY
    }

    private fun createNotificationChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Nova Companion Background Service",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Keeps secure connection to Nova Core active"
            }
            val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            manager.createNotificationChannel(channel)
        }
    }

    private fun buildNotification(): Notification {
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setContentTitle("Nova Companion Active")
            .setContentText("Connected to Nova Core AI Brain")
            .setSmallIcon(R.drawable.ic_launcher_foreground)
            .setPriority(NotificationCompat.PRIORITY_LOW)
            .setOngoing(true)
            .build()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onDestroy() {
        wsClient.disconnect()
        super.onDestroy()
    }
}
