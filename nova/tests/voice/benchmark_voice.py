import time
import numpy as np
import collections

_WAKE_FRAME = 1280
_WAKE_CHUNK = 480
SAMPLE_RATE = 16000
_WAKE_CAPTURE_SECS = 2.0
_cap_len = int(SAMPLE_RATE * _WAKE_CAPTURE_SECS)

class CircularAudioBuffer:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.buffer = np.zeros(capacity, dtype=np.float32)
        self.index = 0
        self.filled = False

    def extend(self, data: np.ndarray):
        n = len(data)
        if n >= self.capacity:
            self.buffer[:] = data[-self.capacity:]
            self.index = 0
            self.filled = True
            return
        
        end = self.index + n
        if end <= self.capacity:
            self.buffer[self.index:end] = data
            self.index = end
        else:
            first_part = self.capacity - self.index
            self.buffer[self.index:] = data[:first_part]
            self.buffer[:n - first_part] = data[first_part:]
            self.index = n - first_part
            self.filled = True

        if self.index >= self.capacity:
            self.index = 0
            self.filled = True

    def get_latest(self) -> np.ndarray:
        if not self.filled:
            return self.buffer[:self.index].copy()
        return np.concatenate((self.buffer[self.index:], self.buffer[:self.index]))

def benchmark_old(num_iterations=1000):
    buf = collections.deque()
    capture = collections.deque(maxlen=_cap_len)
    for _ in range(_cap_len):
        capture.append(0.0)
    frame = np.empty(_WAKE_FRAME, dtype=np.float32)
    dummy_input = np.random.randn(_WAKE_CHUNK).astype(np.float32)
    
    t0 = time.perf_counter()
    for _ in range(num_iterations):
        buf.extend(dummy_input)
        capture.extend(dummy_input)
        while len(buf) >= _WAKE_FRAME:
            for i in range(_WAKE_FRAME):
                frame[i] = buf[i]
            for _ in range(_WAKE_CHUNK):
                buf.popleft()
    t1 = time.perf_counter()
    return t1 - t0

def benchmark_new(num_iterations=1000):
    frame = np.zeros(_WAKE_FRAME, dtype=np.float32)
    capture_buffer = CircularAudioBuffer(_cap_len)
    dummy_input = np.random.randn(_WAKE_CHUNK).astype(np.float32)
    
    t0 = time.perf_counter()
    for _ in range(num_iterations):
        frame[:800] = frame[480:]
        frame[800:] = dummy_input
        capture_buffer.extend(dummy_input)
    t1 = time.perf_counter()
    return t1 - t0

def main():
    print("=== NOVA VOICE BENCHMARK PROFILE ===")
    print("Benchmarking 1000 iterations (approx. 30 seconds of audio)...")
    
    time_old = benchmark_old()
    time_new = benchmark_new()
    
    print(f"Old Deque implementation:            {time_old:.6f} s")
    print(f"New Optimized Buffer implementation: {time_new:.6f} s")
    speedup = time_old / time_new
    print(f"Performance Speedup:                 {speedup:.2f}x")
    print("======================================")

if __name__ == "__main__":
    main()
