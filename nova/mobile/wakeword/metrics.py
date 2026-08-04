"""Wake Word Metrics Python Binding."""

import time


class WakeWordMetrics:
    def __init__(self):
        self.total_detections = 0
        self.last_detection_timestamp = 0.0
        self.total_recovery_attempts = 0
        self.cpu_usage_percent = 1.2
        self.battery_impact_level = "LOW"

    def record_detection(self):
        self.total_detections += 1
        self.last_detection_timestamp = time.time()

    def record_recovery(self):
        self.total_recovery_attempts += 1
