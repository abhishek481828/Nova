package com.nova.mobile.wakeword

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.content.ContextCompat

class MicrophoneManager(private val context: Context) {
    companion object {
        private const val TAG = "MicrophoneManager"
    }

    private var audioRecord: AudioRecord? = null
    var isRecording: Boolean = false
        private set

    fun hasRecordPermission(): Boolean {
        return ContextCompat.checkSelfPermission(
            context,
            Manifest.permission.RECORD_AUDIO
        ) == PackageManager.PERMISSION_GRANTED
    }

    fun startCapturing(sampleRate: Int = 16000, frameSize: Int = 512): Boolean {
        if (!hasRecordPermission()) {
            Log.e(TAG, "Record Audio permission missing!")
            return false
        }

        if (isRecording) {
            Log.w(TAG, "Microphone is already capturing.")
            return true
        }

        return try {
            val minBufferSize = AudioRecord.getMinBufferSize(
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT
            )
            val bufferSize = Math.max(minBufferSize, frameSize * 4)

            audioRecord = AudioRecord(
                MediaRecorder.AudioSource.MIC,
                sampleRate,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize
            )

            if (audioRecord?.state != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "Failed to initialize AudioRecord instance.")
                cleanup()
                return false
            }

            audioRecord?.startRecording()
            isRecording = true
            Log.i(TAG, "Microphone capture started successfully (sampleRate=$sampleRate).")
            true
        } catch (e: Exception) {
            Log.e(TAG, "Error starting microphone capture", e)
            cleanup()
            false
        }
    }

    fun readChunk(buffer: ShortArray): Int {
        if (!isRecording || audioRecord == null) return -1
        return try {
            audioRecord?.read(buffer, 0, buffer.size) ?: -1
        } catch (e: Exception) {
            Log.e(TAG, "Error reading audio chunk from microphone", e)
            -1
        }
    }

    fun stopCapturing() {
        if (!isRecording) return
        Log.i(TAG, "Stopping microphone capture...")
        try {
            audioRecord?.stop()
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping AudioRecord", e)
        } finally {
            cleanup()
        }
    }

    private fun cleanup() {
        try {
            audioRecord?.release()
        } catch (e: Exception) {
            Log.e(TAG, "Error releasing AudioRecord", e)
        }
        audioRecord = null
        isRecording = false
    }
}
