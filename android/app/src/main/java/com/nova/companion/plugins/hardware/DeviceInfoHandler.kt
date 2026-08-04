package com.nova.companion.plugins.hardware

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.net.wifi.WifiManager
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.PowerManager
import android.os.StatFs
import android.util.DisplayMetrics
import android.view.WindowManager
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.net.NetworkInterface

class DeviceInfoHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "system.device"
    override val supportedActions: List<String> = listOf("device.info", "device.health")

    override fun execute(action: String, payload: JSONObject): ActionResult {
        return when (action) {
            "device.info" -> ActionResult("success", data = collectDeviceInfo())
            "device.health" -> ActionResult("success", data = collectDeviceHealth())
            else -> ActionResult("error", error = "Unsupported action: $action")
        }
    }

    fun getFullDeviceInfo(): ActionResult {
        return ActionResult("success", data = collectDeviceInfo())
    }

    fun collectDeviceInfo(): JSONObject {
        val json = JSONObject()
        json.put("device_name", "${Build.MANUFACTURER} ${Build.MODEL}")
        json.put("manufacturer", Build.MANUFACTURER)
        json.put("model", Build.MODEL)
        json.put("android_version", Build.VERSION.RELEASE)
        json.put("sdk_version", Build.VERSION.SDK_INT)

        // CPU Architecture
        val abis = JSONArray()
        for (abi in Build.SUPPORTED_ABIS) {
            abis.put(abi)
        }
        json.put("cpu_architecture", abis)

        // Memory (RAM)
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memInfo = ActivityManager.MemoryInfo()
        am.getMemoryInfo(memInfo)
        json.put("total_ram_bytes", memInfo.totalMem)
        json.put("available_ram_bytes", memInfo.availMem)

        // Storage
        val path = Environment.getDataDirectory()
        val stat = StatFs(path.path)
        val totalStorage = stat.blockCountLong * stat.blockSizeLong
        val availStorage = stat.availableBlocksLong * stat.blockSizeLong
        json.put("total_storage_bytes", totalStorage)
        json.put("available_storage_bytes", availStorage)

        // Screen Resolution & Refresh Rate
        val wm = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        val metrics = DisplayMetrics()
        @Suppress("DEPRECATION")
        wm.defaultDisplay.getMetrics(metrics)
        json.put("screen_width_pixels", metrics.widthPixels)
        json.put("screen_height_pixels", metrics.heightPixels)
        @Suppress("DEPRECATION")
        json.put("screen_refresh_rate_hz", wm.defaultDisplay.refreshRate)

        // IP Address
        json.put("ip_address", getLocalIpAddress())

        return json
    }

    fun collectDeviceHealth(): JSONObject {
        val json = JSONObject()

        // Battery
        val intentFilter = IntentFilter(Intent.ACTION_BATTERY_CHANGED)
        val batteryStatus: Intent? = context.registerReceiver(null, intentFilter)

        val level = batteryStatus?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = batteryStatus?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val batteryPct = if (level >= 0 && scale > 0) (level * 100 / scale.toFloat()).toInt() else 85

        val status = batteryStatus?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val isCharging = status == BatteryManager.BATTERY_STATUS_CHARGING || status == BatteryManager.BATTERY_STATUS_FULL

        val tempTenths = batteryStatus?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 300) ?: 300
        val tempC = tempTenths / 10.0

        json.put("battery_percent", batteryPct)
        json.put("is_charging", isCharging)
        json.put("battery_temp", tempC)

        // Memory Usage %
        val am = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memInfo = ActivityManager.MemoryInfo()
        am.getMemoryInfo(memInfo)
        val ramUsagePct = ((memInfo.totalMem - memInfo.availMem).toDouble() / memInfo.totalMem.toDouble()) * 100.0
        json.put("ram_usage_percent", roundTwo(ramUsagePct))

        // Storage Usage %
        val path = Environment.getDataDirectory()
        val stat = StatFs(path.path)
        val totalStorage = stat.blockCountLong * stat.blockSizeLong
        val availStorage = stat.availableBlocksLong * stat.blockSizeLong
        val storageUsagePct = ((totalStorage - availStorage).toDouble() / totalStorage.toDouble()) * 100.0
        json.put("storage_usage_percent", roundTwo(storageUsagePct))

        // Power & Screen State
        val pm = context.getSystemService(Context.POWER_SERVICE) as PowerManager
        json.put("is_screen_on", pm.isInteractive)
        json.put("is_device_idle", pm.isDeviceIdleMode)

        // Wi-Fi Signal
        val wm = context.applicationContext.getSystemService(Context.WIFI_SERVICE) as WifiManager
        val wifiInfo = wm.connectionInfo
        json.put("wifi_signal_dbm", wifiInfo.rssi)
        json.put("wifi_ssid", wifiInfo.ssid)

        return json
    }

    private fun getLocalIpAddress(): String {
        try {
            val interfaces = NetworkInterface.getNetworkInterfaces()
            while (interfaces.hasMoreElements()) {
                val intf = interfaces.nextElement()
                val addrs = intf.inetAddresses
                while (addrs.hasMoreElements()) {
                    val addr = addrs.nextElement()
                    if (!addr.isLoopbackAddress && addr.hostAddress.indexOf(':') < 0) {
                        return addr.hostAddress
                    }
                }
            }
        } catch (e: Exception) {
            // Ignore
        }
        return "127.0.0.1"
    }

    private fun roundTwo(value: Double): Double {
        return Math.round(value * 100.0) / 100.0
    }
}
