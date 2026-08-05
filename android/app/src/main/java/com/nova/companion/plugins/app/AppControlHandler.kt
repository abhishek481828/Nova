package com.nova.companion.plugins.app

import android.content.Context
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.content.pm.PackageManager
import android.net.Uri
import android.util.Log
import com.nova.companion.accessibility.NovaAccessibilityService
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONArray
import org.json.JSONObject
import java.net.URLEncoder

class AppControlHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "app"
    override val supportedActions: List<String> = listOf(
        "app.launch",
        "app.list",
        "app.is_running",
        "whatsapp.call"
    )

    private val commonPackageMap = mapOf(
        "chrome" to "com.android.chrome",
        "google chrome" to "com.android.chrome",
        "youtube" to "com.google.android.youtube",
        "whatsapp" to "com.whatsapp",
        "settings" to "com.android.settings",
        "calculator" to "com.sec.android.app.popupcalculator",
        "calendar" to "com.samsung.android.calendar",
        "maps" to "com.google.android.apps.maps",
        "google maps" to "com.google.android.apps.maps",
        "gmail" to "com.google.android.gm",
        "camera" to "com.sec.android.app.camera",
        "gallery" to "com.sec.android.gallery3d"
    )

    override fun execute(action: String, payload: JSONObject): ActionResult {
        return when (action) {
            "app.launch" -> launchApp(payload)
            "youtube.play" -> launchYouTubePlay(payload)
            "app.list" -> listInstalledApps(payload.optBoolean("include_system", false))
            "app.is_running" -> isAppRunning(payload.optString("package_name", payload.optString("app_name", "")))
            "whatsapp.call" -> performWhatsAppCall(payload.optString("contact_name", payload.optString("contact", "")))
            else -> ActionResult("error", error = "Unsupported app action: $action")
        }
    }

    private fun launchYouTubePlay(payload: JSONObject): ActionResult {
        val query = payload.optString("query", payload.optString("song_name", payload.optString("search_query", "")))
        val appPayload = JSONObject().apply {
            put("app_name", "youtube")
            put("search_query", if (query.isNotEmpty()) query else "english song")
            put("auto_play", true)
        }
        return launchApp(appPayload)
    }

    private fun launchApp(payload: JSONObject): ActionResult {
        val packageName = payload.optString("package_name", "")
        val appName = payload.optString("app_name", "").trim()
        val searchQuery = payload.optString("search_query", payload.optString("query", "")).trim()
        val contactName = payload.optString("contact_name", payload.optString("contact", "")).trim()
        val operation = payload.optString("operation", "").trim()
        val pm = context.packageManager

        var targetPackage = packageName.trim()

        if (targetPackage.isEmpty() && appName.isNotEmpty()) {
            val appLower = appName.lowercase()
            if (appLower == "youtube" || appLower == "yt") {
                val revanced = "app.revanced.android.youtube"
                if (pm.getLaunchIntentForPackage(revanced) != null) {
                    targetPackage = revanced
                }
            }
            if (targetPackage.isEmpty()) {
                val mapped = commonPackageMap[appLower]
                if (mapped != null && pm.getLaunchIntentForPackage(mapped) != null) {
                    targetPackage = mapped
                }
            }
        }

        if (targetPackage.isEmpty() && appName.isNotEmpty()) {
            val installedApps = pm.getInstalledApplications(PackageManager.GET_META_DATA)
            for (app in installedApps) {
                val label = pm.getApplicationLabel(app).toString()
                if (label.equals(appName, ignoreCase = true)) {
                    if (pm.getLaunchIntentForPackage(app.packageName) != null) {
                        targetPackage = app.packageName
                        break
                    }
                }
            }
            if (targetPackage.isEmpty()) {
                for (app in installedApps) {
                    val label = pm.getApplicationLabel(app).toString()
                    if (label.contains(appName, ignoreCase = true)) {
                        if (pm.getLaunchIntentForPackage(app.packageName) != null) {
                            targetPackage = app.packageName
                            break
                        }
                    }
                }
            }
        }

        // WhatsApp Call / Message Handler
        if ((appName.lowercase().contains("whatsapp") || targetPackage.contains("whatsapp")) && contactName.isNotEmpty()) {
            return performWhatsAppCall(contactName)
        }

        // YouTube Deep-link Search & Auto-Play Handler
        if (searchQuery.isNotEmpty() && (appName.lowercase().contains("youtube") || targetPackage.contains("youtube"))) {
            try {
                val encodedQuery = URLEncoder.encode(searchQuery, "UTF-8")
                val searchUri = Uri.parse("https://www.youtube.com/results?search_query=$encodedQuery")
                val intent = Intent(Intent.ACTION_VIEW, searchUri).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                    if (targetPackage.isNotEmpty()) {
                        setPackage(targetPackage)
                    }
                }
                context.startActivity(intent)

                if (payload.optBoolean("auto_play", true)) {
                    Thread {
                        try {
                            Thread.sleep(3500)
                            val service = NovaAccessibilityService.getInstance()
                            if (service != null) {
                                service.clickFirstVideoResult()
                            }
                        } catch (e: Exception) {
                            Log.e("AppControlHandler", "Auto-play click failed", e)
                        }
                    }.start()
                }

                val data = JSONObject().apply {
                    put("status", "launched_search_and_playing")
                    put("package_name", targetPackage)
                    put("app_name", appName)
                    put("search_query", searchQuery)
                }
                return ActionResult("success", data = data)
            } catch (e: Exception) {
                Log.e("AppControlHandler", "YouTube search deep link failed", e)
            }
        }

        if (targetPackage.isEmpty()) {
            return ActionResult("error", error = "Could not resolve valid launchable package for '$appName'", errorCode = "APP_NOT_FOUND")
        }

        var launchIntent = pm.getLaunchIntentForPackage(targetPackage)
        if (launchIntent == null) {
            launchIntent = Intent(Intent.ACTION_MAIN).apply {
                addCategory(Intent.CATEGORY_LAUNCHER)
                setPackage(targetPackage)
            }
        }

        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
        val accService = NovaAccessibilityService.getInstance()
        if (accService != null) {
            accService.startActivity(launchIntent)
        } else {
            context.startActivity(launchIntent)
        }

        val data = JSONObject().apply {
            put("status", "launched")
            put("package_name", targetPackage)
            put("app_name", if (appName.isNotEmpty()) appName else targetPackage)
        }
        return ActionResult("success", data = data)
    }

    private fun performWhatsAppCall(contactName: String): ActionResult {
        if (contactName.isEmpty()) {
            return ActionResult("error", error = "Missing contact_name for WhatsApp call")
        }
        val pm = context.packageManager
        var pkg = "com.whatsapp"
        if (pm.getLaunchIntentForPackage(pkg) == null && pm.getLaunchIntentForPackage("com.whatsapp.w4b") != null) {
            pkg = "com.whatsapp.w4b"
        }

        val launchIntent = pm.getLaunchIntentForPackage(pkg) ?: Intent(Intent.ACTION_MAIN).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
            setPackage(pkg)
        }
        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED)
        context.startActivity(launchIntent)

        // Execute robust multi-step WhatsApp call macro in background thread
        Thread {
            try {
                Thread.sleep(1800)
                val service = NovaAccessibilityService.getInstance()
                var searchClicked = false
                if (service != null) {
                    searchClicked = service.clickElement("Ask Meta AI or Search") ||
                                    service.clickElement("Search") ||
                                    service.clickElement("com.whatsapp:id/search_text") ||
                                    service.clickElement("com.whatsapp:id/search_bar_inner_layout") ||
                                    service.clickElement("com.whatsapp:id/menuitem_search")
                }

                if (!searchClicked) {
                    // ADB Fallback: tap WhatsApp top search bar (x=540, y=300)
                    Runtime.getRuntime().exec("input tap 540 300")
                }
                Thread.sleep(1000)

                // Type contact name
                var typed = false
                if (service != null) {
                    typed = service.typeText("Ask Meta AI or Search", contactName, true) ||
                            service.typeText("Search…", contactName, true) ||
                            service.typeText("Search", contactName, true) ||
                            service.typeText("com.whatsapp:id/search_src_text", contactName, true)
                }

                if (!typed) {
                    // ADB Fallback: type text via input
                    val safeContact = contactName.replace(" ", "%s")
                    Runtime.getRuntime().exec("input text $safeContact")
                }
                Thread.sleep(1500)

                // Select contact item
                var contactClicked = false
                if (service != null) {
                    contactClicked = service.clickElement(contactName)
                }
                if (!contactClicked) {
                    // ADB Fallback: tap top search result card (x=540, y=500)
                    Runtime.getRuntime().exec("input tap 540 500")
                }
                Thread.sleep(1500)

                // Click Voice Call icon
                var callClicked = false
                if (service != null) {
                    callClicked = service.clickElement("Voice call") ||
                                  service.clickElement("Call") ||
                                  service.clickElement("com.whatsapp:id/voice_call") ||
                                  service.clickElement("com.whatsapp:id/call_button")
                }
                if (!callClicked) {
                    // ADB Fallback: tap top-right voice call icon in chat header (x=920, y=160)
                    Runtime.getRuntime().exec("input tap 920 160")
                }
            } catch (e: Exception) {
                Log.e("AppControlHandler", "Error executing WhatsApp call macro", e)
            }
        }.start()

        val data = JSONObject().apply {
            put("status", "call_initiated")
            put("contact_name", contactName)
            put("package_name", pkg)
        }
        return ActionResult("success", data = data)
    }

    private fun listInstalledApps(includeSystem: Boolean): ActionResult {
        val pm = context.packageManager
        val apps = pm.getInstalledApplications(PackageManager.GET_META_DATA)
        val appList = JSONArray()

        for (app in apps) {
            val isSystem = (app.flags and ApplicationInfo.FLAG_SYSTEM) != 0
            val launchable = pm.getLaunchIntentForPackage(app.packageName) != null
            if (!includeSystem && (!launchable || isSystem)) continue

            val label = pm.getApplicationLabel(app).toString()
            val item = JSONObject().apply {
                put("app_name", label)
                put("package_name", app.packageName)
                put("is_system", isSystem)
                put("launchable", launchable)
            }
            appList.put(item)
        }

        val data = JSONObject().apply {
            put("total_apps", appList.length())
            put("apps", appList)
        }
        return ActionResult("success", data = data)
    }

    private fun isAppRunning(query: String): ActionResult {
        if (query.isEmpty()) {
            return ActionResult("error", error = "Missing package_name or app_name")
        }

        val service = NovaAccessibilityService.getInstance()
        var isRunning = false
        var currentPkg = ""

        if (service != null) {
            val tree = service.dumpUiTree()
            currentPkg = tree.optString("package_name", "")
            if (currentPkg.equals(query, ignoreCase = true) || currentPkg.contains(query, ignoreCase = true)) {
                isRunning = true
            }
        }

        val data = JSONObject().apply {
            put("query", query)
            put("is_running", isRunning)
            put("active_foreground_package", currentPkg)
        }
        return ActionResult("success", data = data)
    }
}
