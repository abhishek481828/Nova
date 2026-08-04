package com.nova.companion.streaming

import android.annotation.SuppressLint
import android.media.*
import android.util.Log
import com.nova.companion.transport.WebSocketClientManager
import okio.ByteString
import okio.ByteString.Companion.toByteString
import java.io.ByteArrayOutputStream
import java.nio.ByteBuffer
import java.nio.ByteOrder

class AudioStreamManager(
    private val wsClient: WebSocketClientManager
) {
    companion object {
        private const val SAMPLE_RATE = 16000
        private const val CHANNEL_IN_CONFIG = AudioFormat.CHANNEL_IN_MONO
        private const val CHANNEL_OUT_CONFIG = AudioFormat.CHANNEL_OUT_MONO
        private const val AUDIO_FORMAT = AudioFormat.ENCODING_PCM_16BIT
        private const val FRAME_HEADER_AUDIO: Byte = 0x0A
    }

    private var audioRecord: AudioRecord? = null
    private var audioTrack: AudioTrack? = null
    private var isRecording = false
    private var isPlaying = false
    private var seqNum = 0

    @SuppressLint("MissingPermission")
    fun startMicrophoneStream() {
        if (isRecording) return

        val minBufferSize = AudioRecord.getMinBufferSize(SAMPLE_RATE, CHANNEL_IN_CONFIG, AUDIO_FORMAT)
        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            SAMPLE_RATE,
            CHANNEL_IN_CONFIG,
            AUDIO_FORMAT,
            minBufferSize * 2
        )

        isRecording = true
        audioRecord?.startRecording()

        Thread {
            val buffer = ByteArray(640) // 20ms chunk (16000 * 2 bytes * 0.02 = 640)
            while (isRecording) {
                val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                if (read > 0) {
                    val binaryFrame = packAudioBinaryFrame(++seqNum, System.currentTimeMillis(), buffer, read)
                    wsClient.sendBinary(binaryFrame.toByteString(0, binaryFrame.size))
                }
            }
        }.start()
        Log.i("AudioStreamManager", "16kHz PCM Microphone Stream Started")
    }

    fun stopMicrophoneStream() {
        isRecording = false
        try {
            audioRecord?.stop()
            audioRecord?.release()
        } catch (e: Exception) {
            Log.e("AudioStreamManager", "Error stopping AudioRecord: ${e.message}")
        }
        audioRecord = null
    }

    fun initSpeakerPlayback() {
        if (isPlaying) return
        val minBufferSize = AudioTrack.getMinBufferSize(SAMPLE_RATE, CHANNEL_OUT_CONFIG, AUDIO_FORMAT)
        audioTrack = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_MEDIA)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setEncoding(AUDIO_FORMAT)
                    .setSampleRate(SAMPLE_RATE)
                    .setChannelMask(CHANNEL_OUT_CONFIG)
                    .build()
            )
            .setBufferSizeInBytes(minBufferSize * 2)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()

        audioTrack?.play()
        isPlaying = true
    }

    fun playAudioFrame(pcmBytes: ByteArray) {
        if (!isPlaying || audioTrack == null) {
            initSpeakerPlayback()
        }
        audioTrack?.write(pcmBytes, 0, pcmBytes.size)
    }

    fun stopSpeakerPlayback() {
        isPlaying = false
        try {
            audioTrack?.stop()
            audioTrack?.release()
        } catch (e: Exception) {
            Log.e("AudioStreamManager", "Error stopping AudioTrack: ${e.message}")
        }
        audioTrack = null
    }

    private fun packAudioBinaryFrame(seq: Int, ts: Long, payload: ByteArray, length: Int): ByteArray {
        val bos = ByteArrayOutputStream()
        bos.write(FRAME_HEADER_AUDIO.toInt())
        val bb = ByteBuffer.allocate(12).order(ByteOrder.BIG_ENDIAN)
        bb.putInt(seq)
        bb.putLong(ts)
        bos.write(bb.array())
        bos.write(payload, 0, length)
        return bos.toByteArray()
    }
}
