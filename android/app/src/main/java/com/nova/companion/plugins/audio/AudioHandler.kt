package com.nova.companion.plugins.audio

import android.content.Context
import android.media.AudioManager
import android.util.Base64
import android.util.Log
import com.nova.companion.plugins.ActionResult
import com.nova.companion.plugins.BaseActionHandler
import org.json.JSONObject

class AudioHandler(private val context: Context) : BaseActionHandler {

    companion object {
        private const val TAG = "AudioHandler"
    }

    private val streamManager = AudioStreamManager(context)
    private val playbackManager = AudioPlaybackManager(context)
    private val voiceSessionManager = VoiceSessionManager(context, streamManager)
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager

    private var isMicMuted = false
    private var isSpeakerMuted = false
    private var savedVolumeLevel = -1

    override val category: String = "audio"
    override val supportedActions: List<String> = listOf(
        "audio.start_capture",
        "audio.stop_capture",
        "audio.stream.start",
        "audio.stream.stop",
        "audio.play",
        "audio.stop",
        "voice.start_session",
        "voice.stop_session",
        "microphone.mute",
        "microphone.unmute",
        "speaker.volume.get",
        "speaker.volume.set",
        "speaker.mute",
        "speaker.unmute"
    )

    override fun execute(action: String, payload: JSONObject): ActionResult {
        Log.i(TAG, "Executing audio action: '$action' with payload: $payload")
        return try {
            when (action) {
                "audio.start_capture", "audio.stream.start" -> startCapture(payload)
                "audio.stop_capture", "audio.stream.stop" -> stopCapture()
                "audio.play" -> playSpeech(payload)
                "audio.stop" -> stopSpeech()
                "voice.start_session" -> startVoiceSession()
                "voice.stop_session" -> stopVoiceSession()
                "microphone.mute" -> setMicrophoneMute(true)
                "microphone.unmute" -> setMicrophoneMute(false)
                "speaker.volume.get" -> getSpeakerVolume()
                "speaker.volume.set" -> setSpeakerVolume(payload.optInt("level", 80))
                "speaker.mute" -> setSpeakerMute(true)
                "speaker.unmute" -> setSpeakerMute(false)
                else -> ActionResult("error", error = "Unsupported audio action: $action", errorCode = "INVALID_ACTION")
            }
        } catch (e: Exception) {
            Log.e(TAG, "Error executing audio action '$action': ${e.message}", e)
            ActionResult("error", error = "Audio action failed: ${e.message}", errorCode = "EXECUTION_FAILURE")
        }
    }

    private fun startCapture(payload: JSONObject): ActionResult {
        val bitrate = payload.optInt("bitrate", 256000)
        val success = streamManager.startCapture(bitrate)
        if (success) {
            val telemetry = streamManager.getTelemetry()
            return ActionResult("success", data = telemetry)
        }
        return ActionResult("error", error = "Failed to start audio capture", errorCode = "CAPTURE_FAILED")
    }

    private fun stopCapture(): ActionResult {
        val base64Pcm = streamManager.getLastRecordedPcmBase64()
        val telemetry = streamManager.getTelemetry()
        telemetry.put("pcm_base64", base64Pcm)
        streamManager.stopCapture()
        return ActionResult("success", data = telemetry)
    }

    private fun playSpeech(payload: JSONObject): ActionResult {
        val base64Pcm = payload.optString("audio_data", payload.optString("base64", ""))
        val sampleRate = payload.optInt("sample_rate", 16000)

        val pcmBytes = if (base64Pcm.isNotEmpty()) {
            try {
                Base64.decode(base64Pcm, Base64.DEFAULT)
            } catch (e: Exception) {
                ByteArray(3200) // Synthetic 100ms tone fallback
            }
        } else {
            ByteArray(3200)
        }

        val success = playbackManager.playAudio(pcmBytes, sampleRate)
        if (success) {
            val data = JSONObject().apply {
                put("status", "playing")
                put("sample_rate", sampleRate)
                put("data_bytes", pcmBytes.size)
            }
            return ActionResult("success", data = data)
        }
        return ActionResult("error", error = "Playback initialization failed", errorCode = "PLAYBACK_FAILED")
    }

    private fun stopSpeech(): ActionResult {
        playbackManager.stopPlayback()
        val data = JSONObject().apply { put("status", "stopped") }
        return ActionResult("success", data = data)
    }

    private fun startVoiceSession(): ActionResult {
        val data = voiceSessionManager.startSession()
        return ActionResult("success", data = data)
    }

    private fun stopVoiceSession(): ActionResult {
        val data = voiceSessionManager.stopSession()
        return ActionResult("success", data = data)
    }

    private fun setMicrophoneMute(mute: Boolean): ActionResult {
        audioManager.isMicrophoneMute = mute
        isMicMuted = mute
        val data = JSONObject().apply {
            put("muted", mute)
        }
        return ActionResult("success", data = data)
    }

    private fun getSpeakerVolume(): ActionResult {
        val current = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC)
        val max = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
        val percent = ((current.toDouble() / max) * 100).toInt()

        val data = JSONObject().apply {
            put("volume_percent", percent)
            put("current_level", current)
            put("max_level", max)
            put("is_muted", isSpeakerMuted)
        }
        return ActionResult("success", data = data)
    }

    private fun setSpeakerVolume(percent: Int): ActionResult {
        val clampedPercent = percent.coerceIn(0, 100)
        val max = audioManager.getStreamMaxVolume(AudioManager.STREAM_MUSIC)
        val target = ((clampedPercent.toDouble() / 100) * max).toInt()

        audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, target, 0)

        val data = JSONObject().apply {
            put("volume_percent", clampedPercent)
            put("level_set", target)
            put("max_level", max)
        }
        return ActionResult("success", data = data)
    }

    private fun setSpeakerMute(mute: Boolean): ActionResult {
        if (mute) {
            savedVolumeLevel = audioManager.getStreamVolume(AudioManager.STREAM_MUSIC)
            audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, 0, 0)
            isSpeakerMuted = true
        } else {
            val restoreLevel = if (savedVolumeLevel >= 0) savedVolumeLevel else 10
            audioManager.setStreamVolume(AudioManager.STREAM_MUSIC, restoreLevel, 0)
            isSpeakerMuted = false
        }
        val data = JSONObject().apply {
            put("muted", mute)
        }
        return ActionResult("success", data = data)
    }
}
