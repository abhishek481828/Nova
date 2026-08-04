package com.nova.mobile.scheduler

import android.content.Context
import android.util.Log
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledFuture
import java.util.concurrent.TimeUnit

enum class TaskPriority { LOW, MEDIUM, HIGH, CRITICAL }

data class MobileTask(
    val id: String,
    val name: String,
    val priority: TaskPriority = TaskPriority.MEDIUM,
    val initialDelayMs: Long = 0L,
    val periodMs: Long = 0L,
    val maxRetries: Int = 3,
    val action: () -> Boolean
)

class TaskScheduler(private val context: Context) {
    companion object {
        private const val TAG = "TaskScheduler"
    }

    private val executor = Executors.newScheduledThreadPool(4)
    private val scheduledTasks = ConcurrentHashMap<String, ScheduledFuture<*>>()
    
    var isRunning: Boolean = false
        private set

    fun initialize() {
        Log.i(TAG, "Initializing TaskScheduler...")
        isRunning = true
    }

    fun scheduleImmediate(task: MobileTask): String {
        executor.execute {
            executeTaskWithRetry(task)
        }
        return task.id
    }

    fun scheduleDelayed(task: MobileTask): String {
        val future = executor.schedule({
            executeTaskWithRetry(task)
        }, task.initialDelayMs, TimeUnit.MILLISECONDS)
        scheduledTasks[task.id] = future
        return task.id
    }

    fun schedulePeriodic(task: MobileTask): String {
        val future = executor.scheduleAtFixedRate({
            executeTaskWithRetry(task)
        }, task.initialDelayMs, task.periodMs, TimeUnit.MILLISECONDS)
        scheduledTasks[task.id] = future
        return task.id
    }

    fun cancelTask(taskId: String): Boolean {
        val future = scheduledTasks.remove(taskId) ?: return false
        return future.cancel(true)
    }

    fun cancelAll() {
        for ((id, future) in scheduledTasks) {
            future.cancel(true)
        }
        scheduledTasks.clear()
        isRunning = false
    }

    private fun executeTaskWithRetry(task: MobileTask) {
        var attempts = 0
        var success = false
        while (attempts < task.maxRetries && !success) {
            attempts++
            try {
                success = task.action()
            } catch (e: Exception) {
                Log.e(TAG, "Task ${task.name} attempt $attempts failed", e)
            }
        }
        if (success) {
            Log.i(TAG, "Task ${task.name} completed successfully on attempt $attempts")
        } else {
            Log.e(TAG, "Task ${task.name} failed after $attempts attempts")
        }
    }
}
