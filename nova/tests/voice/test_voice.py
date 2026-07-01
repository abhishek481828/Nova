import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# Ensure project path is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

try:
    import numpy as np
    from nova.voice.config import *
    from nova.voice.pipeline import record_audio, calculate_rms
    from nova.voice.whisper import NebiusSTTProvider
    from nova.voice.tts import EdgeTTSProvider
    from nova.voice.wakeword import LocalWakeWordDetector, NovaRuleDetector
    from nova.voice.pipeline import HighPassFilter, AutomaticGainControl, WebRTCVoiceActivityDetector, AmbientCalibrator
    _NUMPY_AVAILABLE = True
except ImportError:
    np = None  # type: ignore
    _NUMPY_AVAILABLE = False

@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestRecorder(unittest.TestCase):

    def test_calculate_rms(self):
        arr = np.array([0.0, 0.0, 0.0])
        self.assertEqual(calculate_rms(arr), 0.0)
        
        arr2 = np.array([1.0, -1.0, 1.0, -1.0])
        self.assertEqual(calculate_rms(arr2), 1.0)

    @patch("sounddevice.InputStream")
    @patch("time.sleep")
    @patch("time.time")
    def test_record_audio_success(self, mock_time, mock_sleep, mock_input_stream):
        import numpy as np
        current_time = 1000.0
        def mock_time_impl():
            nonlocal current_time
            val = current_time
            current_time += 0.01
            return val
        mock_time.side_effect = mock_time_impl
        
        chunk_idx = 0
        def mock_sleep_impl(duration):
            nonlocal chunk_idx, current_time
            args, kwargs = mock_input_stream.call_args
            callback = kwargs.get("callback")
            blocksize = kwargs.get("blocksize", 480)
            if callback:
                if chunk_idx == 0:
                    callback(np.zeros((blocksize, 1), dtype=np.float32), blocksize, None, None)
                elif chunk_idx == 1:
                    callback(np.ones((blocksize, 1), dtype=np.float32) * 0.1, blocksize, None, None)
                else:
                    current_time += 5.0  # Fast forward to trigger silence timeout
                    callback(np.zeros((blocksize, 1), dtype=np.float32), blocksize, None, None)
                chunk_idx += 1
        mock_sleep.side_effect = mock_sleep_impl
        
        mock_instance = MagicMock()
        mock_input_stream.return_value = mock_instance
        mock_instance.__enter__.return_value = mock_instance
        
        res = record_audio()
        self.assertIsInstance(res, bytes)
        self.assertTrue(res.startswith(b"RIFF")) # In-memory WAV header check

    @patch("sounddevice.InputStream")
    def test_record_audio_import_error(self, mock_input_stream):
        with patch.dict(sys.modules, {'sounddevice': None}):
            with self.assertRaises(RuntimeError) as context:
                record_audio()
            self.assertIn("Microphone or audio system not available", str(context.exception))

@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestAudioProcessor(unittest.TestCase):

    def test_highpass_filter(self):
        import numpy as np
        filt = HighPassFilter(cutoff=80.0, fs=16000)
        
        # Feed DC offset (0Hz constant signal)
        dc_signal = np.ones((500, 1), dtype=np.float32) * 0.5
        filtered = filt.process(dc_signal)
        
        # Verify the DC component is significantly decayed
        self.assertLess(np.abs(filtered[-1, 0]), 0.05)

    def test_agc_gain_adjustment(self):
        import numpy as np
        agc = AutomaticGainControl(target_level=0.5, max_gain=10.0, rate=1.0) # instant rate for test
        
        quiet_signal = np.ones((100, 1), dtype=np.float32) * 0.05
        processed = agc.process(quiet_signal)
        
        # The quiet signal should be scaled up close to the target of 0.5
        self.assertAlmostEqual(np.max(np.abs(processed)), 0.5, delta=0.05)

    def test_webrtc_vad_fallback(self):
        import numpy as np
        vad = WebRTCVoiceActivityDetector(aggressiveness=2, default_threshold=0.01)
        
        # Silence chunk should trigger False
        silent_chunk = np.zeros((480, 1), dtype=np.float32)
        self.assertFalse(vad.is_speech(silent_chunk, 16000))

    def test_ambient_calibration(self):
        import numpy as np
        calibrator = AmbientCalibrator()
        
        # Input constant noise at 0.01 level
        noise = np.ones((32000, 1), dtype=np.float32) * 0.01
        calibrator.calibrate(noise)
        
        self.assertAlmostEqual(calibrator.noise_floor, 0.01, delta=0.001)
        self.assertGreater(calibrator.speech_threshold, 0.01)



@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestWakeWord(unittest.TestCase):
    def test_rule_detector_syllables(self):
        import numpy as np
        detector = NovaRuleDetector(wake_word="nova", confidence_threshold=0.5)
        self.assertEqual(detector.wake_word, "nova")
        
        short_buf = np.zeros((10, 1), dtype=np.float32)
        self.assertFalse(detector.detect(short_buf, 16000))
        
    def test_unified_detector_factory(self):
        detector = LocalWakeWordDetector(wake_word="nova")
        self.assertIsInstance(detector.detector, NovaRuleDetector)

@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestSTT(unittest.TestCase):

    @patch("httpx.Client")
    def test_nebius_stt_success(self, mock_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"text": "hello nova"}
        
        mock_client.return_value.post.return_value = mock_resp
        mock_client.return_value.__enter__.return_value.post.return_value = mock_resp
        
        provider = NebiusSTTProvider(api_key="test-key")
        result = provider.transcribe(b"dummy wav data")
        self.assertEqual(result, "hello nova")

    @patch("httpx.Client")
    def test_nebius_stt_http_client_error_no_retry(self, mock_client):
        import httpx
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        
        mock_client.return_value.post.side_effect = httpx.HTTPStatusError(
            "Auth failed", request=MagicMock(), response=mock_resp
        )
        mock_client.return_value.__enter__.return_value.post.side_effect = httpx.HTTPStatusError(
            "Auth failed", request=MagicMock(), response=mock_resp
        )
        
        provider = NebiusSTTProvider(api_key="test-key", max_retries=3)
        with self.assertRaises(Exception) as context:
            provider.transcribe(b"dummy wav data")
        
        call_count = mock_client.return_value.post.call_count or mock_client.return_value.__enter__.return_value.post.call_count
        self.assertEqual(call_count, 1)
        self.assertIn("client error 401", str(context.exception))

    @patch("httpx.Client")
    @patch("time.sleep")
    def test_nebius_stt_server_error_retry(self, mock_sleep, mock_client):
        import httpx
        mock_resp_fail = MagicMock()
        mock_resp_fail.status_code = 500
        mock_resp_fail.text = "Internal Server Error"
        
        mock_resp_success = MagicMock()
        mock_resp_success.status_code = 200
        mock_resp_success.json.return_value = {"text": "recovered hello"}
        
        mock_client.return_value.post.side_effect = [
            httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_resp_fail),
            httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_resp_fail),
            mock_resp_success
        ]
        mock_client.return_value.__enter__.return_value.post.side_effect = [
            httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_resp_fail),
            httpx.HTTPStatusError("Server error", request=MagicMock(), response=mock_resp_fail),
            mock_resp_success
        ]
        
        provider = NebiusSTTProvider(api_key="test-key", max_retries=3)
        result = provider.transcribe(b"dummy wav data")
        
        self.assertEqual(result, "recovered hello")
        call_count = mock_client.return_value.post.call_count or mock_client.return_value.__enter__.return_value.post.call_count
        self.assertEqual(call_count, 3)
        self.assertEqual(mock_sleep.call_count, 2)

@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed - skipping voice tests")
class TestTTS(unittest.TestCase):

    @patch("subprocess.Popen")
    @patch("os.path.exists")
    @patch("os.remove")
    @patch("soundfile.read")
    @patch("sounddevice.play")
    def test_tts_speak_success(self, mock_sd_play, mock_sf_read, mock_remove, mock_exists, mock_popen):
        mock_sf_read.side_effect = Exception("soundfile mock error")
        mock_exists.return_value = True
        
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        mock_popen.return_value = mock_proc
        
        mock_communicate = MagicMock()
        async def mock_save(path):
            pass
        mock_communicate.save = mock_save
        
        with patch("edge_tts.Communicate", return_value=mock_communicate):
            provider = EdgeTTSProvider()
            provider.speak("hello")
            
            mock_popen.assert_called_once()
            self.assertEqual(mock_popen.call_args[0][0][0], "mpg123")

if __name__ == "__main__":
    unittest.main()
