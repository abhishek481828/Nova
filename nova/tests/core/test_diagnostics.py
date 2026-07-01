"""
Regression tests for nova.voice.pipeline.VoiceDiagnosticsEngine.

Covers:
  - Wake success / false wake / missed wake counter correctness
  - Success rate calculation
  - Turn latency stats (avg, min, max, p95)
  - Audio quality snapshot aggregation
  - Noise history bounded deque
  - Speaker confidence stats
  - Resource usage dict shape
  - Text report contains all sections
  - JSON report is valid and has all keys
  - save_report writes file
  - Thread safety under concurrent writes
  - Module-level get_diagnostics() accessor
"""

import sys
import os
import json
import time
import threading
import unittest
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../../../")))

try:
    from nova.voice.pipeline import VoiceDiagnosticsEngine
    _NUMPY_AVAILABLE = True
except ImportError:
    VoiceDiagnosticsEngine = None  # type: ignore
    _NUMPY_AVAILABLE = False


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestWakeStats(unittest.TestCase):

    def setUp(self):
        self.d = VoiceDiagnosticsEngine()

    def test_success_counter(self):
        self.d.record_wake_success(score=0.82, latency_ms=145.0)
        self.d.record_wake_success(score=0.91, latency_ms=120.0)
        stats = self.d.get_wake_stats()
        self.assertEqual(stats["success_count"], 2)
        self.assertAlmostEqual(stats["avg_wake_score"], 0.865, places=3)
        self.assertAlmostEqual(stats["avg_wake_latency_ms"], 132.5, places=1)

    def test_false_wake_counter(self):
        self.d.record_false_wake(score=0.48, noise_floor=0.01)
        self.d.record_false_wake(score=0.51, noise_floor=0.02)
        stats = self.d.get_wake_stats()
        self.assertEqual(stats["false_wake_count"], 2)

    def test_missed_wake_counter(self):
        self.d.record_missed_wake(score=0.39, noise_floor=0.005)
        stats = self.d.get_wake_stats()
        self.assertEqual(stats["missed_wake_count"], 1)

    def test_success_rate(self):
        self.d.record_wake_success(score=0.8, latency_ms=100.0)
        self.d.record_wake_success(score=0.9, latency_ms=110.0)
        self.d.record_false_wake(score=0.4, noise_floor=0.01)
        stats = self.d.get_wake_stats()
        # 2 successes out of 3 total triggers = 0.6667
        self.assertAlmostEqual(stats["success_rate"], 2 / 3, places=3)

    def test_empty_stats(self):
        stats = self.d.get_wake_stats()
        self.assertEqual(stats["success_count"], 0)
        self.assertEqual(stats["success_rate"], 0.0)


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestLatencyStats(unittest.TestCase):

    def setUp(self):
        self.d = VoiceDiagnosticsEngine()

    def test_avg_and_bounds(self):
        latencies = [100.0, 200.0, 300.0, 400.0, 500.0]
        for l in latencies:
            self.d.record_turn(latency_ms=l, stt_latency_ms=l * 0.5)
        stats = self.d.get_latency_stats()
        self.assertEqual(stats["turn_count"], 5)
        self.assertAlmostEqual(stats["e2e_avg_ms"], 300.0, places=1)
        self.assertAlmostEqual(stats["e2e_min_ms"], 100.0, places=1)
        self.assertAlmostEqual(stats["e2e_max_ms"], 500.0, places=1)

    def test_p95(self):
        # 100 values 1..100; p95 should be around 95
        for i in range(1, 101):
            self.d.record_turn(latency_ms=float(i))
        stats = self.d.get_latency_stats()
        self.assertGreater(stats["e2e_p95_ms"], 90.0)

    def test_empty_latency(self):
        stats = self.d.get_latency_stats()
        self.assertEqual(stats["turn_count"], 0)
        self.assertEqual(stats["e2e_avg_ms"], 0.0)


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestAudioQualityStats(unittest.TestCase):

    def setUp(self):
        self.d = VoiceDiagnosticsEngine()

    def test_aggregation(self):
        for snr in [10.0, 20.0, 30.0]:
            self.d.record_audio_quality({
                "snr_db": snr,
                "background_noise": 0.002,
                "clipping_pct": 0.0,
                "voice_volume": 0.05,
                "echo_level": 0.01,
                "overall_quality": 0.85,
            })
        stats = self.d.get_audio_quality_stats()
        self.assertEqual(stats["snapshot_count"], 3)
        self.assertAlmostEqual(stats["avg_snr_db"], 20.0, places=3)

    def test_empty(self):
        stats = self.d.get_audio_quality_stats()
        self.assertEqual(stats["snapshot_count"], 0)
        self.assertEqual(stats["avg_overall_quality"], 0.0)


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestNoiseHistory(unittest.TestCase):

    def setUp(self):
        self.d = VoiceDiagnosticsEngine()

    def test_history_returns_values(self):
        for v in [0.01, 0.02, 0.03]:
            self.d.record_noise_sample(v)
        hist = self.d.get_noise_history(n=10)
        self.assertEqual(len(hist), 3)
        self.assertAlmostEqual(hist[-1], 0.03, places=4)

    def test_history_bounded(self):
        # VoiceDiagnosticsEngine deque max = 500
        for i in range(600):
            self.d.record_noise_sample(float(i))
        hist = self.d.get_noise_history(n=1000)
        self.assertLessEqual(len(hist), 500)

    def test_history_n_limit(self):
        for i in range(100):
            self.d.record_noise_sample(float(i))
        hist = self.d.get_noise_history(n=10)
        self.assertEqual(len(hist), 10)


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestSpeakerConfidenceStats(unittest.TestCase):

    def setUp(self):
        self.d = VoiceDiagnosticsEngine()

    def test_stats_populated(self):
        scores = [0.60, 0.75, 0.80, 0.90, 0.95]
        for s in scores:
            self.d.record_turn(latency_ms=100.0, speaker_confidence=s)
        stats = self.d.get_speaker_confidence_stats()
        self.assertEqual(stats["sample_count"], 5)
        self.assertAlmostEqual(stats["min"], 0.60, places=3)
        self.assertAlmostEqual(stats["max"], 0.95, places=3)
        self.assertGreater(stats["p95"], 0.90)

    def test_empty(self):
        stats = self.d.get_speaker_confidence_stats()
        self.assertEqual(stats["sample_count"], 0)


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestResourceUsage(unittest.TestCase):

    def test_shape(self):
        d = VoiceDiagnosticsEngine()
        res = d.get_resource_usage()
        self.assertIn("cpu_pct", res)
        self.assertIn("memory_mb", res)
        self.assertIn("thread_count", res)
        # memory_mb must be a positive number if available
        if res["memory_mb"] is not None:
            self.assertGreater(res["memory_mb"], 0.0)


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestReportGeneration(unittest.TestCase):

    def _populated_engine(self):
        d = VoiceDiagnosticsEngine()
        d.record_wake_success(0.85, 130.0)
        d.record_false_wake(0.45, 0.01)
        d.record_missed_wake(0.38, 0.008)
        d.record_turn(latency_ms=950.0, stt_latency_ms=310.0,
                      audio_quality=0.82, speaker_confidence=0.79,
                      noise_floor=0.003)
        d.record_audio_quality({
            "snr_db": 22.5, "background_noise": 0.003,
            "clipping_pct": 0.0, "voice_volume": 0.04,
            "echo_level": 0.02, "overall_quality": 0.82,
        })
        d.record_noise_sample(0.003)
        return d

    def test_text_report_sections(self):
        d = self._populated_engine()
        report = d.generate_report(fmt="text")
        for section in ["Wake-Word", "Latency", "Audio Quality",
                        "Speaker Confidence", "Ambient Noise", "Resource Usage"]:
            self.assertIn(section, report, f"Missing section: {section}")

    def test_text_report_values(self):
        d = self._populated_engine()
        report = d.generate_report(fmt="text")
        self.assertIn("1", report)   # success count
        self.assertIn("950", report) # e2e latency

    def test_json_report_valid(self):
        d = self._populated_engine()
        raw = d.generate_report(fmt="json")
        obj = json.loads(raw)  # must not raise
        for key in ["wake", "latency", "audio_quality", "speaker",
                    "noise_history", "resource_usage", "session_uptime_s"]:
            self.assertIn(key, obj, f"Missing JSON key: {key}")

    def test_save_report(self):
        d = self._populated_engine()
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "test_report.txt")
            result_path = d.save_report(path=path)
            self.assertEqual(result_path, path)
            self.assertTrue(os.path.exists(path))
            with open(path) as fh:
                content = fh.read()
            self.assertIn("Wake-Word", content)


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestThreadSafety(unittest.TestCase):

    def test_concurrent_writes(self):
        d = VoiceDiagnosticsEngine()
        errors = []

        def writer():
            try:
                for _ in range(50):
                    d.record_wake_success(0.8, 120.0)
                    d.record_false_wake(0.4, 0.01)
                    d.record_noise_sample(0.005)
                    d.record_turn(latency_ms=500.0)
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=writer) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        self.assertEqual(errors, [], f"Thread safety errors: {errors}")
        stats = d.get_wake_stats()
        self.assertEqual(stats["success_count"], 8 * 50)


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestModuleAccessor(unittest.TestCase):

    def test_get_diagnostics_before_loop(self):
        """get_diagnostics() returns None when voice loop hasn't set active_diagnostics."""
        import nova.voice.config as cfg
        original = cfg.active_diagnostics
        cfg.active_diagnostics = None
        try:
            from nova.voice import get_diagnostics
            result = get_diagnostics()
            self.assertIsNone(result)
        finally:
            cfg.active_diagnostics = original

    def test_get_diagnostics_returns_instance(self):
        import nova.voice.config as cfg
        d = VoiceDiagnosticsEngine()
        cfg.active_diagnostics = d
        try:
            from nova.voice import get_diagnostics
            result = get_diagnostics()
            self.assertIs(result, d)
        finally:
            cfg.active_diagnostics = None


@unittest.skipUnless(_NUMPY_AVAILABLE, "numpy not installed — skipping voice tests")
class TestAsyncLogger(unittest.TestCase):

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.log_path = os.path.join(self.tmp_dir.name, "test_async_logs.json")

    def tearDown(self):
        from nova.voice.pipeline import _async_logger
        _async_logger.flush()
        self.tmp_dir.cleanup()

    def test_async_logger_writes_event(self):
        from nova.voice.pipeline import async_log, _async_logger
        
        # Log event enqueues safely
        event = {"ts": time.time(), "event": "test_event", "score": 0.8}
        async_log(self.log_path, event, max_entries=10)
        
        # Flush synchronously
        _async_logger.flush()
        
        # Verify file contents
        self.assertTrue(os.path.exists(self.log_path))
        with open(self.log_path, "r") as f:
            logs = json.load(f)
            
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["event"], "test_event")
        self.assertAlmostEqual(logs[0]["score"], 0.8)

    def test_async_logger_caps_history(self):
        from nova.voice.pipeline import async_log, _async_logger
        
        # Submit 15 logs, cap at 10
        for i in range(15):
            async_log(self.log_path, {"val": i}, max_entries=10)
            
        _async_logger.flush()
        
        # Verify file exists and has exactly 10 logs
        self.assertTrue(os.path.exists(self.log_path))
        with open(self.log_path, "r") as f:
            logs = json.load(f)
            
        self.assertEqual(len(logs), 10)
        # Should be the last 10 logs (5 to 14)
        self.assertEqual(logs[0]["val"], 5)
        self.assertEqual(logs[-1]["val"], 14)


if __name__ == "__main__":
    unittest.main()
