package com.nova.companion.plugins.system

import android.content.Context
import android.content.Intent
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONArray
import org.json.JSONObject

class AppLauncherHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "system.apps"
    override val supportedActions: List<String> = listOf("app.launch", "app.list")

    override fun execute(action: String, payload: JSONObject): ActionResult {
        return when (action) {
            "app.list" -> listInstalledApps()
            "app.launch" -> launchApp(payload.optString("package_name"))
            else -> ActionResult("error", error = "Unsupported app action")
        }
    }

    private fun listInstalledApps(): ActionResult {
        val pm = context.packageManager
        val intent = Intent(Intent.ACTION_MAIN, null).apply {
            addCategory(Intent.CATEGORY_LAUNCHER)
        }
        val apps = pm.queryIntentActivities(intent, 0)
        val array = JSONArray()
        for (app in apps) {
            val appJson = JSONObject().apply {
                put("label", app.loadLabel(pm).toString())
                put("package_name", app.activityInfo.packageName)
            }
            array.put(appJson)
        }
        val data = JSONObject().apply {
            put("apps", array)
        }
        return ActionResult("success", data = data)
    }

    private fun launchApp(packageName: String?): ActionResult {
        if (packageName.isNullOrEmpty()) {
            return ActionResult("error", error = "Package name is required to launch app")
        }
        val pm = context.packageManager
        val launchIntent = pm.getLaunchIntentForPackage(packageName)
            ?: return ActionResult("error", error = "App $packageName not found or has no launch activity")

        launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(launchIntent)

        val data = JSONObject().apply {
            put("package_name", packageName)
            put("status", "launched")
        }
        return ActionResult("success", data = data)
    }
}
