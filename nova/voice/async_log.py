import os
import json
import queue
import threading
import atexit
from typing import Tuple, Dict, List
from nova.logger import logger

class AsyncLogger:
    def __init__(self, flush_interval_secs: float = 1.0) -> None:
        self._queue: queue.Queue[Tuple[str, dict, int]] = queue.Queue()
        self._buffers: Dict[str, List[dict]] = {}
        self._max_lens: Dict[str, int] = {}
        self._lock = threading.Lock()
        self._disk_lock = threading.Lock()
        self._flush_lock = threading.Lock()
        self._flush_interval = flush_interval_secs
        self._stop_event = threading.Event()
        
        self._worker_thread = threading.Thread(
            target=self._worker_loop,
            daemon=True,
            name="nova_async_logging_worker"
        )
        self._worker_thread.start()
        atexit.register(self.shutdown)

    def log(self, file_path: str, entry: dict, max_entries: int = 500) -> None:
        norm_path = os.path.abspath(os.path.expanduser(file_path))
        logger.debug(f"[AsyncLogger.log] Enqueuing log event: {entry.get('event')} to {norm_path}")
        self._queue.put((norm_path, entry, max_entries))

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                item = self._queue.get(timeout=self._flush_interval)
                self._buffer_item(item)
                
                while not self._queue.empty():
                    item = self._queue.get_nowait()
                    self._buffer_item(item)
                    self._queue.task_done()
                    
                self._queue.task_done()
            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Error in async logging worker: {e}")
                
            self.flush()

    def _buffer_item(self, item: Tuple[str, dict, int]) -> None:
        file_path, entry, max_entries = item
        with self._lock:
            if file_path not in self._buffers:
                self._buffers[file_path] = []
            self._buffers[file_path].append(entry)
            self._max_lens[file_path] = max_entries

    def flush(self) -> None:
        if not hasattr(self, '_flush_lock'):
            self._flush_lock = threading.Lock()
        with self._flush_lock:
            while not self._queue.empty():
                try:
                    item = self._queue.get_nowait()
                    self._buffer_item(item)
                    self._queue.task_done()
                except queue.Empty:
                    break

            with self._lock:
                if not self._buffers:
                    return
                buffers_to_flush = dict(self._buffers)
                self._buffers.clear()
                max_lens = dict(self._max_lens)
                
            for file_path, new_entries in buffers_to_flush.items():
                max_len = max_lens.get(file_path, 500)
                self._write_to_disk(file_path, new_entries, max_len)

    def _write_to_disk(self, file_path: str, new_entries: List[dict], max_len: int) -> None:
        if not hasattr(self, '_disk_lock'):
            self._disk_lock = threading.Lock()
        with self._disk_lock:
            logs = []
            if os.path.exists(file_path):
                try:
                    with open(file_path, "r") as f:
                        logs = json.load(f)
                        if not isinstance(logs, list):
                            logs = []
                except Exception as e:
                    logger.debug(f"[_write_to_disk] Error reading existing file: {e}")
                    logs = []
                    
            logs.extend(new_entries)
            logs = logs[-max_len:]
            
            try:
                os.makedirs(os.path.dirname(file_path), exist_ok=True)
                temp_path = file_path + ".tmp"
                with open(temp_path, "w") as f:
                    json.dump(logs, f, indent=2)
                os.replace(temp_path, file_path)
            except Exception as e:
                logger.debug(f"Failed async write to {file_path}: {e}")

    def shutdown(self) -> None:
        if self._stop_event.is_set():
            return
        self._stop_event.set()
        while not self._queue.empty():
            try:
                item = self._queue.get_nowait()
                self._buffer_item(item)
                self._queue.task_done()
            except queue.Empty:
                break
        self.flush()
        try:
            self._worker_thread.join(timeout=1.0)
        except Exception:
            pass

_async_logger = AsyncLogger()

def async_log(file_path: str, entry: dict, max_entries: int = 500) -> None:
    _async_logger.log(file_path, entry, max_entries)
