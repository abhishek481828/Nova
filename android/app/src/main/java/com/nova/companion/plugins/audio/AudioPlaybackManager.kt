package com.nova.companion.plugins.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.util.Log
import com.nova.companion.event.EventBus
import org.json.JSONObject
import java.util.concurrent.atomic.AtomicBoolean

class AudioPlaybackManager(private val context: Context) {

    companion object {
        private const val TAG = "AudioPlaybackManager"
    }

    private val isPlaying = AtomicBoolean(false)
    private var audioTrack: AudioTrack? = null
    private var playbackThread: Thread? = null

    fun playAudio(pcmData: ByteArray, sampleRate: Int = 16000): Boolean {
        stopPlayback()

        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        audioManager.mode = AudioManager.MODE_NORMAL
        audioManager.isSpeakerphoneOn = true

        val bufferSize = AudioTrack.getMinBufferSize(
            sampleRate,
            AudioFormat.CHANNEL_OUT_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        ).coerceAtLeast(pcmData.size)

        try {
            audioTrack = AudioTrack.Builder()
                .setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                .setAudioFormat(
                    AudioFormat.Builder()
                        .setEncoding(AudioFormat.ENCODING_PCM_16BIT)
                        .setSampleRate(sampleRate)
                        .setChannelMask(AudioFormat.CHANNEL_OUT_MONO)
                        .build()
                )
                .setBufferSizeInBytes(bufferSize)
                .setTransferMode(AudioTrack.MODE_STREAM)
                .build()

            audioTrack?.play()
            isPlaying.set(true)

            EventBus.publish("Playback Started", JSONObject().apply {
                put("sample_rate", sampleRate)
                put("data_size_bytes", pcmData.size)
            })

            playbackThread = Thread {
                try {
                    audioTrack?.write(pcmData, 0, pcmData.size)
                    audioTrack?.stop()
                } catch (e: Exception) {
                    Log.e(TAG, "Error writing audio to AudioTrack", e)
                } finally {
                    isPlaying.set(false)
                    EventBus.publish("Playback Finished", JSONObject().apply {
                        put("status", "completed")
                    })
                }
            }.apply {
                isDaemon = true
                start()
            }

            Log.i(TAG, "Playing TTS audio stream (${pcmData.size} bytes at $sampleRate Hz)")
            return true
        } catch (e: Exception) {
            Log.e(TAG, "Error initializing AudioTrack for playback", e)
            isPlaying.set(false)
            return false
        }
    }

    fun stopPlayback(): Boolean {
        if (!isPlaying.get()) return true

        isPlaying.set(false)
        playbackThread?.interrupt()
        playbackThread = null

        try {
            audioTrack?.stop()
            audioTrack?.release()
            audioTrack = null
        } catch (e: Exception) {
            Log.e(TAG, "Error stopping AudioTrack", e)
        }

        EventBus.publish("Playback Finished", JSONObject().apply {
            put("status", "stopped")
        })

        Log.i(TAG, "TTS audio playback stopped")
        return true
    }

    fun isPlaying(): Boolean = isPlaying.get()
}
