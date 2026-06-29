import threading
import asyncio
from nova.dashboard.backend.server import start_server, stop_server
from nova.logger import logger

_server_thread: threading.Thread | None = None

def start_dashboard(port: int = 11436) -> None:
    """Launch the dashboard aiohttp server in a dedicated background thread."""
    global _server_thread
    if _server_thread is not None and _server_thread.is_alive():
        logger.warning("Dashboard server is already running.")
        return
        
    def thread_target():
        # Set up a clean event loop for this thread and run start_server
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(start_server(port))
        except Exception as e:
            logger.error(f"Error in dashboard event loop: {e}")
        finally:
            loop.close()
            logger.info("Dashboard event loop closed.")
        
    _server_thread = threading.Thread(target=thread_target, name="DashboardThread", daemon=True)
    _server_thread.start()
    logger.info(f"Dashboard server thread launched in background on port {port}.")

def stop_dashboard() -> None:
    """Stop the dashboard server and wait for its thread to finish."""
    logger.info("Stopping dashboard server...")
    stop_server()
    global _server_thread
    if _server_thread is not None:
        _server_thread.join(timeout=2.0)
        logger.info("Dashboard server thread stopped.")
        _server_thread = None
