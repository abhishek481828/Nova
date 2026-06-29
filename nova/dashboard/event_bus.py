import asyncio
from datetime import datetime, timezone
from typing import Any, Dict

_server_loop: asyncio.AbstractEventLoop | None = None
_ws_manager: Any = None

def register_dashboard_context(loop: asyncio.AbstractEventLoop, ws_manager: Any) -> None:
    """Register the active dashboard server loop and websocket manager."""
    global _server_loop, _ws_manager
    _server_loop = loop
    _ws_manager = ws_manager

def unregister_dashboard_context() -> None:
    """Clear registered context on shutdown."""
    global _server_loop, _ws_manager
    _server_loop = None
    _ws_manager = None

def emit(event: str, module: str = "core", status: str = "success", metadata: Dict[str, Any] = None) -> None:
    """
    Emit a structured event to the dashboard.
    Thread-safe and non-blocking. Safe to call from any thread.
    """
    global _server_loop, _ws_manager
    if _server_loop is None or _ws_manager is None:
        return
        
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat() + "Z",
        "module": module,
        "event": event,
        "status": status,
        "metadata": metadata or {}
    }
    
    try:
        if _server_loop.is_running():
            asyncio.run_coroutine_threadsafe(
                _ws_manager.broadcast(payload),
                _server_loop
            )
    except Exception:
        # Ignore errors to ensure core app is never broken by dashboard reporting
        pass
