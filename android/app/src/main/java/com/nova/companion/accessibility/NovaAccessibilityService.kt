package com.nova.companion.accessibility

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.AccessibilityServiceInfo
import android.content.Context
import android.content.Intent
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import org.json.JSONArray
import org.json.JSONObject
import java.lang.ref.WeakReference

class NovaAccessibilityService : AccessibilityService() {

    companion object {
        private const val TAG = "NovaAccessibility"
        private var instanceRef: WeakReference<NovaAccessibilityService>? = null

        val isServiceRunning: Boolean
            get() = instanceRef?.get() != null

        fun getInstance(): NovaAccessibilityService? {
            return instanceRef?.get()
        }

        fun isAccessibilityEnabled(context: Context): Boolean {
            val am = context.getSystemService(Context.ACCESSIBILITY_SERVICE) as? android.view.accessibility.AccessibilityManager
            val enabledServices = am?.getEnabledAccessibilityServiceList(AccessibilityServiceInfo.FEEDBACK_GENERIC)
            if (enabledServices != null) {
                for (service in enabledServices) {
                    if (service.resolveInfo.serviceInfo.packageName == context.packageName &&
                        service.resolveInfo.serviceInfo.name == NovaAccessibilityService::class.java.name) {
                        return true
                    }
                }
            }
            return isServiceRunning
        }
    }

    private var currentPackageName: String = ""
    private var currentClassName: String = ""

    override fun onServiceConnected() {
        super.onServiceConnected()
        instanceRef = WeakReference(this)
        Log.i(TAG, "NovaAccessibilityService connected and operational")
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return

        when (event.eventType) {
            AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED,
            AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED -> {
                event.packageName?.let { currentPackageName = it.toString() }
                event.className?.let { currentClassName = it.toString() }
            }
        }
    }

    override fun onInterrupt() {
        Log.w(TAG, "NovaAccessibilityService interrupted")
    }

    override fun onDestroy() {
        super.onDestroy()
        instanceRef = null
        Log.i(TAG, "NovaAccessibilityService destroyed")
    }

    /**
     * Traverses the active window hierarchy and returns a structured JSON tree.
     */
    fun dumpUiTree(): JSONObject {
        val rootNode = rootInActiveWindow
            ?: return JSONObject().apply {
                put("error", "No active window root node available")
                put("package_name", currentPackageName)
            }

        val result = JSONObject().apply {
            put("package_name", currentPackageName)
            put("class_name", currentClassName)
            put("root", nodeToJson(rootNode))
        }
        return result
    }

    private fun nodeToJson(node: AccessibilityNodeInfo?): JSONObject {
        if (node == null) return JSONObject()

        val json = JSONObject()
        json.put("text", node.text?.toString() ?: "")
        json.put("content_description", node.contentDescription?.toString() ?: "")
        json.put("view_id", node.viewIdResourceName ?: "")
        json.put("class_name", node.className?.toString() ?: "")
        json.put("clickable", node.isClickable)
        json.put("editable", node.isEditable)
        json.put("enabled", node.isEnabled)
        json.put("scrollable", node.isScrollable)
        json.put("focused", node.isFocused)

        val bounds = android.graphics.Rect()
        node.getBoundsInScreen(bounds)
        json.put("bounds", JSONObject().apply {
            put("left", bounds.left)
            put("top", bounds.top)
            put("right", bounds.right)
            put("bottom", bounds.bottom)
            put("width", bounds.width())
            put("height", bounds.height())
        })

        val children = JSONArray()
        for (i in 0 until node.childCount) {
            val child = node.getChild(i)
            if (child != null) {
                children.put(nodeToJson(child))
            }
        }
        json.put("children", children)

        return json
    }

    /**
     * Finds and clicks a UI node matching target query (text, viewId, or contentDescription).
     */
    fun clickElement(target: String): Boolean {
        val rootNode = rootInActiveWindow ?: return false
        val matchingNode = findNode(rootNode, target) ?: return false

        var currentNode: AccessibilityNodeInfo? = matchingNode
        while (currentNode != null) {
            if (currentNode.isClickable) {
                val success = currentNode.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                if (success) return true
            }
            currentNode = currentNode.parent
        }
        return false
    }

    /**
     * Finds an editable field and inputs specified text.
     */
    fun typeText(target: String?, text: String, replace: Boolean = true): Boolean {
        val rootNode = rootInActiveWindow ?: return false
        val targetNode = if (!target.isNull_orEmpty()) {
            findNode(rootNode, target!!)
        } else {
            findFocusedOrEditableNode(rootNode)
        } ?: return false

        val arguments = android.os.Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        return targetNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)
    }

    private fun findFocusedOrEditableNode(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null) return null
        if (node.isFocused && node.isEditable) return node
        if (node.isEditable) return node

        for (i in 0 until node.childCount) {
            val result = findFocusedOrEditableNode(node.getChild(i))
            if (result != null) return result
        }
        return null
    }

    /**
     * Traverses hierarchy to find a matching AccessibilityNodeInfo.
     */
    private fun findNode(node: AccessibilityNodeInfo?, target: String): AccessibilityNodeInfo? {
        if (node == null) return null

        val text = node.text?.toString() ?: ""
        val contentDesc = node.contentDescription?.toString() ?: ""
        val viewId = node.viewIdResourceName ?: ""

        if (text.equals(target, ignoreCase = true) || text.contains(target, ignoreCase = true) ||
            contentDesc.equals(target, ignoreCase = true) || contentDesc.contains(target, ignoreCase = true) ||
            viewId.endsWith(target, ignoreCase = true)) {
            return node
        }

        for (i in 0 until node.childCount) {
            val result = findNode(node.getChild(i), target)
            if (result != null) return result
        }
        return null
    }

    /**
     * Scrolls active window in specified direction.
     */
    fun scroll(direction: String): Boolean {
        val rootNode = rootInActiveWindow ?: return false
        val scrollableNode = findScrollableNode(rootNode) ?: return false

        val action = when (direction.lowercase()) {
            "down", "forward" -> AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
            "up", "backward" -> AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
            else -> AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
        }
        return scrollableNode.performAction(action)
    }

    private fun findScrollableNode(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
        if (node == null) return null
        if (node.isScrollable) return node

        for (i in 0 until node.childCount) {
            val result = findScrollableNode(node.getChild(i))
            if (result != null) return result
        }
        return null
    }

    /**
     * Finds and clicks the first video card in active window search results.
     */
    fun clickFirstVideoResult(): Boolean {
        val rootNode = rootInActiveWindow ?: return false
        val clickableList = ArrayList<AccessibilityNodeInfo>()
        collectClickableNodes(rootNode, clickableList)

        for (node in clickableList) {
            val text = (node.text ?: node.contentDescription ?: "").toString()
            val viewId = node.viewIdResourceName ?: ""
            if (viewId.contains("thumbnail") || viewId.contains("title") || viewId.contains("item") || text.contains("views") || text.length > 5) {
                if (node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                    return true
                }
            }
        }

        for (node in clickableList) {
            val viewId = node.viewIdResourceName ?: ""
            if (!viewId.contains("search") && !viewId.contains("button") && !viewId.contains("menu")) {
                if (node.performAction(AccessibilityNodeInfo.ACTION_CLICK)) {
                    return true
                }
            }
        }
        return false
    }

    private fun collectClickableNodes(node: AccessibilityNodeInfo?, list: MutableList<AccessibilityNodeInfo>) {
        if (node == null) return
        if (node.isClickable && node.isVisibleToUser) {
            list.add(node)
        }
        for (i in 0 until node.childCount) {
            collectClickableNodes(node.getChild(i), list)
        }
    }

    /**
     * Performs a tap, long press, or double tap gesture at (x, y) coordinates using dispatchGesture.
     */
    fun performTap(x: Float, y: Float, durationMs: Long = 100L, doubleTap: Boolean = false): Boolean {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.N) return false
        val path = android.graphics.Path().apply {
            moveTo(x, y)
        }
        val stroke = android.accessibilityservice.GestureDescription.StrokeDescription(path, 0L, durationMs)
        val gesture = android.accessibilityservice.GestureDescription.Builder().addStroke(stroke).build()

        var success = false
        val latch = java.util.concurrent.CountDownLatch(1)
        dispatchGesture(gesture, object : AccessibilityService.GestureResultCallback() {
            override fun onCompleted(gestureDescription: android.accessibilityservice.GestureDescription?) {
                success = true
                latch.countDown()
            }
            override fun onCancelled(gestureDescription: android.accessibilityservice.GestureDescription?) {
                success = false
                latch.countDown()
            }
        }, null)
        try {
            latch.await(1000, java.util.concurrent.TimeUnit.MILLISECONDS)
        } catch (e: Exception) {
            Log.e(TAG, "Gesture latch interrupted", e)
        }

        if (doubleTap && success) {
            Thread.sleep(100)
            return performTap(x, y, durationMs, false)
        }
        return success
    }

    /**
     * Performs a swipe gesture from (startX, startY) to (endX, endY) using dispatchGesture.
     */
    fun performSwipe(startX: Float, startY: Float, endX: Float, endY: Float, durationMs: Long = 300L): Boolean {
        if (android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.N) return false
        val path = android.graphics.Path().apply {
            moveTo(startX, startY)
            lineTo(endX, endY)
        }
        val stroke = android.accessibilityservice.GestureDescription.StrokeDescription(path, 0L, durationMs)
        val gesture = android.accessibilityservice.GestureDescription.Builder().addStroke(stroke).build()

        var success = false
        val latch = java.util.concurrent.CountDownLatch(1)
        dispatchGesture(gesture, object : AccessibilityService.GestureResultCallback() {
            override fun onCompleted(gestureDescription: android.accessibilityservice.GestureDescription?) {
                success = true
                latch.countDown()
            }
            override fun onCancelled(gestureDescription: android.accessibilityservice.GestureDescription?) {
                success = false
                latch.countDown()
            }
        }, null)
        try {
            latch.await(1000, java.util.concurrent.TimeUnit.MILLISECONDS)
        } catch (e: Exception) {
            Log.e(TAG, "Gesture latch interrupted", e)
        }
        return success
    }
}

private fun String?.isNull_orEmpty(): Boolean = this == null || this.isEmpty()
