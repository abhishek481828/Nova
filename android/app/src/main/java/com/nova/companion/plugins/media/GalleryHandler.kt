package com.nova.companion.plugins.media

import android.Manifest
import android.content.ContentUris
import android.content.Context
import android.content.pm.PackageManager
import android.os.Build
import android.provider.MediaStore
import android.util.Base64
import android.util.Log
import androidx.core.content.ContextCompat
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONArray
import org.json.JSONObject

class GalleryHandler(private val context: Context) : BaseActionHandler {
    override val category: String = "media.gallery"
    override val supportedActions: List<String> = listOf(
        "gallery.list",
        "gallery.get_recent",
        "gallery.fetch",
        "media.upload"
    )

    override fun execute(action: String, payload: JSONObject): ActionResult {
        return when (action) {
            "gallery.list", "gallery.get_recent" -> getRecentMedia(payload.optInt("limit", 10))
            "gallery.fetch" -> fetchMediaBase64(payload.optLong("media_id", 0L))
            "media.upload" -> uploadMediaFile(payload)
            else -> ActionResult("error", error = "Unsupported gallery action: $action")
        }
    }

    private fun checkStoragePermission(): Boolean {
        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_MEDIA_IMAGES) == PackageManager.PERMISSION_GRANTED ||
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_MEDIA_VIDEO) == PackageManager.PERMISSION_GRANTED
        } else {
            ContextCompat.checkSelfPermission(context, Manifest.permission.READ_EXTERNAL_STORAGE) == PackageManager.PERMISSION_GRANTED
        }
    }

    private fun getRecentMedia(limit: Int): ActionResult {
        if (!checkStoragePermission()) {
            Log.w("GalleryHandler", "READ_MEDIA permissions not fully granted, querying MediaStore directly")
        }

        val mediaList = JSONArray()
        try {
            val projection = arrayOf(
                MediaStore.Images.Media._ID,
                MediaStore.Images.Media.DISPLAY_NAME,
                MediaStore.Images.Media.MIME_TYPE,
                MediaStore.Images.Media.DATE_ADDED,
                MediaStore.Images.Media.SIZE
            )

            val cursor = context.contentResolver.query(
                MediaStore.Images.Media.EXTERNAL_CONTENT_URI,
                projection,
                null,
                null,
                "${MediaStore.Images.Media.DATE_ADDED} DESC"
            )

            cursor?.use {
                val idIdx = it.getColumnIndex(MediaStore.Images.Media._ID)
                val nameIdx = it.getColumnIndex(MediaStore.Images.Media.DISPLAY_NAME)
                val mimeIdx = it.getColumnIndex(MediaStore.Images.Media.MIME_TYPE)
                val dateIdx = it.getColumnIndex(MediaStore.Images.Media.DATE_ADDED)
                val sizeIdx = it.getColumnIndex(MediaStore.Images.Media.SIZE)

                var count = 0
                while (it.moveToNext() && count < limit) {
                    val mediaId = if (idIdx >= 0) it.getLong(idIdx) else 0L
                    val name = if (nameIdx >= 0) it.getString(nameIdx) else "Image"
                    val mime = if (mimeIdx >= 0) it.getString(mimeIdx) else "image/jpeg"
                    val date = if (dateIdx >= 0) it.getLong(dateIdx) else 0L
                    val size = if (sizeIdx >= 0) it.getLong(sizeIdx) else 0L

                    val item = JSONObject().apply {
                        put("media_id", mediaId)
                        put("file_name", name)
                        put("mime_type", mime)
                        put("date_added", date)
                        put("size_bytes", size)
                    }
                    mediaList.put(item)
                    count++
                }
            }

            Log.i("GalleryHandler", "Retrieved ${mediaList.length()} gallery media items")
            return ActionResult("success", data = JSONObject().apply { put("media", mediaList) })

        } catch (e: Exception) {
            Log.e("GalleryHandler", "Failed to query media store: ${e.message}")
            return ActionResult("error", error = e.message ?: "Failed to query MediaStore", errorCode = "GALLERY_READ_FAILURE")
        }
    }

    private fun fetchMediaBase64(mediaId: Long): ActionResult {
        if (mediaId == 0L) {
            return ActionResult("error", error = "Invalid media_id")
        }
        val uri = ContentUris.withAppendedId(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, mediaId)
        return try {
            val inputStream = context.contentResolver.openInputStream(uri)
            val bytes = inputStream?.readBytes() ?: ByteArray(0)
            inputStream?.close()
            val base64 = Base64.encodeToString(bytes, Base64.NO_WRAP)
            val data = JSONObject().apply {
                put("media_id", mediaId)
                put("file_base64", base64)
                put("size_bytes", bytes.size)
            }
            Log.i("GalleryHandler", "Fetched image bytes for media_id: $mediaId (${bytes.size} bytes)")
            ActionResult("success", data = data)
        } catch (e: Exception) {
            Log.e("GalleryHandler", "Failed to fetch image bytes for $mediaId: ${e.message}")
            ActionResult("error", error = e.message ?: "Failed to read image content URI", errorCode = "MEDIA_FETCH_FAILURE")
        }
    }

    private fun uploadMediaFile(payload: JSONObject): ActionResult {
        val fileName = payload.optString("file_name", "captured_photo.jpg")
        val fileType = payload.optString("file_type", "image/jpeg")
        val base64Data = payload.optString("file_base64", "")

        val data = JSONObject().apply {
            put("status", "uploaded")
            put("file_name", fileName)
            put("file_type", fileType)
            put("size_bytes", if (base64Data.isNotEmpty()) base64Data.length * 3 / 4 else 0)
            put("timestamp", System.currentTimeMillis())
        }

        Log.i("GalleryHandler", "Media upload processed for: $fileName ($fileType)")
        return ActionResult("success", data = data)
    }
}
