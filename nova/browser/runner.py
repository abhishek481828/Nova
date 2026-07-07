import queue
import threading
import logging
from concurrent.futures import Future
from typing import Callable, Any, Dict

logger = logging.getLogger("nova.browser.runner")

class BrowserRunner:
    """
    A thread-safe runner that delegates all browser automation tasks
    to a single dedicated background thread. This avoids Playwright
    threading violations while enabling fast in-process execution.
    """
    _thread = None
    _queue = queue.Queue()
    _running = False
    _lock = threading.Lock()

    @classmethod
    def start(cls) -> None:
        """Starts the dedicated browser worker thread if not already running."""
        with cls._lock:
            if cls._running:
                return
            cls._running = True
            cls._thread = threading.Thread(target=cls._run_loop, name="BrowserRunnerThread", daemon=True)
            cls._thread.start()
            logger.info("BrowserRunner background thread started.")

    @classmethod
    def stop(cls) -> None:
        """Stops the worker thread."""
        with cls._lock:
            if not cls._running:
                return
            cls._running = False
            cls._queue.put(None)
            if cls._thread:
                cls._thread.join(timeout=3.0)
            cls._thread = None
            logger.info("BrowserRunner background thread stopped.")

    @classmethod
    def execute(cls, fn: Callable[..., Any], *args, **kwargs) -> Any:
        """
        Executes a browser automation function in the dedicated runner thread.
        Blocks the calling thread and returns the result, or raises the exception if failed.
        """
        if not cls._running:
            cls.start()
        
        future = Future()
        cls._queue.put((fn, args, kwargs, future))
        return future.result()

    @classmethod
    def submit(cls, fn: Callable[..., Any], *args, **kwargs) -> Future:
        """
        Submits a browser automation function to the dedicated runner thread.
        Returns a Future immediately without blocking the calling thread.
        """
        if not cls._running:
            cls.start()
        
        future = Future()
        cls._queue.put((fn, args, kwargs, future))
        return future

    @classmethod
    def _run_loop(cls) -> None:
        try:
            while cls._running:
                task = cls._queue.get()
                if task is None:
                    cls._queue.task_done()
                    break
                
                fn, args, kwargs, future = task
                try:
                    res = fn(*args, **kwargs)
                    future.set_result(res)
                except Exception as e:
                    logger.error(f"BrowserRunner task execution failed: {e}", exc_info=True)
                    future.set_exception(e)
                finally:
                    cls._queue.task_done()
        except Exception as e:
            logger.error(f"Error in BrowserRunner thread: {e}", exc_info=True)
        finally:
            logger.info("Cleaning up Playwright in BrowserRunner thread.")
            try:
                from nova.browser.manager import BrowserManager
                BrowserManager.close_connection()
            except Exception:
                pass
