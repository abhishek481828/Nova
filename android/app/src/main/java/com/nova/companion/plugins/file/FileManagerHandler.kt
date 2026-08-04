package com.nova.companion.plugins.file

import android.content.Context
import android.util.Base64
import com.nova.companion.event.EventBus
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream

/**
 * Phase I: Secure File Manager Handler.
 */
class FileManagerHandler(private val context: Context) : BaseActionHandler {

    override val category: String = "file"

    override val supportedActions: List<String> = listOf(
        "file.list",
        "file.upload",
        "file.download",
        "file.delete",
        "file.rename",
        "file.move",
        "file.copy"
    )

    override fun execute(action: String, payload: JSONObject): ActionResult {
        return try {
            when (action) {
                "file.list" -> {
                    val pathStr = payload.optString("path", "/sdcard")
                    val files = listFiles(pathStr)
                    val data = JSONObject()
                    data.put("path", pathStr)
                    data.put("files", files)
                    data.put("total", files.length())
                    ActionResult("success", data)
                }
                "file.upload" -> {
                    val targetPath = payload.optString("path", "")
                    val b64Content = payload.optString("content_b64", "")
                    val append = payload.optBoolean("append", false)
                    if (targetPath.isEmpty()) {
                        return ActionResult("error", error = "Missing target path")
                    }
                    val bytesWritten = uploadFile(targetPath, b64Content, append)
                    EventBus.publish("File Upload Completed", JSONObject().put("path", targetPath).put("bytes", bytesWritten))
                    val data = JSONObject()
                    data.put("path", targetPath)
                    data.put("bytes_written", bytesWritten)
                    ActionResult("success", data)
                }
                "file.download" -> {
                    val sourcePath = payload.optString("path", "")
                    if (sourcePath.isEmpty()) {
                        return ActionResult("error", error = "Missing source path")
                    }
                    val fileData = downloadFile(sourcePath)
                    EventBus.publish("File Download Completed", JSONObject().put("path", sourcePath))
                    ActionResult("success", fileData)
                }
                "file.delete" -> {
                    val targetPath = payload.optString("path", "")
                    val success = deleteFile(targetPath)
                    if (success) {
                        ActionResult("success", JSONObject().put("message", "File or directory deleted successfully."))
                    } else {
                        ActionResult("error", error = "Failed to delete file or path does not exist.")
                    }
                }
                "file.rename" -> {
                    val oldPath = payload.optString("path", "")
                    val newName = payload.optString("new_name", "")
                    val success = renameFile(oldPath, newName)
                    if (success) {
                        ActionResult("success", JSONObject().put("message", "Renamed successfully."))
                    } else {
                        ActionResult("error", error = "Rename failed.")
                    }
                }
                "file.move" -> {
                    val sourcePath = payload.optString("source", "")
                    val destPath = payload.optString("destination", "")
                    val success = moveFile(sourcePath, destPath)
                    if (success) {
                        ActionResult("success", JSONObject().put("message", "Moved successfully."))
                    } else {
                        ActionResult("error", error = "Move failed.")
                    }
                }
                "file.copy" -> {
                    val sourcePath = payload.optString("source", "")
                    val destPath = payload.optString("destination", "")
                    val success = copyFile(sourcePath, destPath)
                    if (success) {
                        ActionResult("success", JSONObject().put("message", "Copied successfully."))
                    } else {
                        ActionResult("error", error = "Copy failed.")
                    }
                }
                else -> ActionResult("error", error = "Unsupported action: $action")
            }
        } catch (e: Exception) {
            ActionResult("error", error = e.message ?: "File manager error")
        }
    }

    private fun listFiles(pathStr: String): JSONArray {
        val array = JSONArray()
        val dir = File(pathStr)
        if (dir.exists() && dir.isDirectory) {
            val list = dir.listFiles()
            if (list != null) {
                for (f in list) {
                    val item = JSONObject()
                    item.put("name", f.name)
                    item.put("path", f.absolutePath)
                    item.put("is_dir", f.isDirectory)
                    item.put("size", f.length())
                    item.put("last_modified", f.lastModified())
                    item.put("can_read", f.canRead())
                    item.put("can_write", f.canWrite())
                    array.put(item)
                }
            }
        } else if (dir.exists() && dir.isFile) {
            val item = JSONObject()
            item.put("name", dir.name)
            item.put("path", dir.absolutePath)
            item.put("is_dir", false)
            item.put("size", dir.length())
            item.put("last_modified", dir.lastModified())
            array.put(item)
        }
        return array
    }

    private fun uploadFile(targetPath: String, b64Content: String, append: Boolean): Int {
        val file = File(targetPath)
        file.parentFile?.mkdirs()
        val bytes = Base64.decode(b64Content, Base64.DEFAULT)
        val fos = FileOutputStream(file, append)
        fos.write(bytes)
        fos.flush()
        fos.close()
        return bytes.size
    }

    private fun downloadFile(sourcePath: String): JSONObject {
        val res = JSONObject()
        val file = File(sourcePath)
        if (!file.exists() || !file.isFile) {
            throw IllegalArgumentException("File not found or is a directory: $sourcePath")
        }
        val fis = FileInputStream(file)
        val bytes = fis.readBytes()
        fis.close()
        val b64 = Base64.encodeToString(bytes, Base64.NO_WRAP)
        res.put("content_b64", b64)
        res.put("size_bytes", bytes.size)
        return res
    }

    private fun deleteFile(pathStr: String): Boolean {
        val file = File(pathStr)
        if (!file.exists()) return false
        return file.deleteRecursively()
    }

    private fun renameFile(oldPath: String, newName: String): Boolean {
        val file = File(oldPath)
        if (!file.exists()) return false
        val dest = File(file.parentFile, newName)
        return file.renameTo(dest)
    }

    private fun moveFile(sourcePath: String, destPath: String): Boolean {
        val src = File(sourcePath)
        val dst = File(destPath)
        if (!src.exists()) return false
        dst.parentFile?.mkdirs()
        return src.renameTo(dst)
    }

    private fun copyFile(sourcePath: String, destPath: String): Boolean {
        val src = File(sourcePath)
        val dst = File(destPath)
        if (!src.exists()) return false
        dst.parentFile?.mkdirs()
        src.copyTo(dst, overwrite = true)
        return true
    }
}
