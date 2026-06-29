import os
import asyncio
import psutil
from aiohttp import web
from pathlib import Path
from nova.dashboard.websocket.manager import WebSocketManager
from nova.dashboard.event_bus import register_dashboard_context, unregister_dashboard_context
from nova.logger import logger

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "frontend" / "dist" / "assets"
TEMPLATES_DIR = BASE_DIR / "frontend" / "dist"

ws_manager = WebSocketManager()
_active_loop: asyncio.AbstractEventLoop | None = None
_runner: web.AppRunner | None = None

def get_event_loop() -> asyncio.AbstractEventLoop | None:
    return _active_loop

def get_ws_manager() -> WebSocketManager:
    return ws_manager

async def index_handler(request: web.Request) -> web.StreamResponse:
    """Serve the dashboard single page application HTML shell."""
    index_path = TEMPLATES_DIR / "index.html"
    if not index_path.exists():
        return web.Response(text="Dashboard HTML template not found.", status=404)
    return web.FileResponse(index_path)

async def forward_text_to_daemon(text: str) -> None:
    """Forwards text command to Nova daemon on TCP port 11435."""
    import json
    try:
        reader, writer = await asyncio.open_connection("127.0.0.1", 11435)
        
        from nova.utils import resolve_chromium_bin
        resolved_chromium = resolve_chromium_bin()
        payload = {
            "query": text,
            "env": dict(os.environ),
            "chromium_bin": resolved_chromium,
            "chrome_bin": resolved_chromium
        }
        message = f"NOVA_JSON:{json.dumps(payload)}"
        writer.write(message.encode("utf-8"))
        await writer.drain()
        
        # Read response to let daemon process completely
        await reader.read(-1)
        writer.close()
        await writer.wait_closed()
    except Exception as e:
        logger.debug(f"Failed to forward command to daemon: {e}")

async def ws_handler(request: web.Request) -> web.WebSocketResponse:
    """Handle incoming client WebSocket connections."""
    ws = web.WebSocketResponse()
    await ws.prepare(request)
    
    await ws_manager.register(ws)
    
    try:
        async for msg in ws:
            if msg.type == web.WSMsgType.TEXT:
                try:
                    import json
                    data = json.loads(msg.data)
                    if isinstance(data, dict) and data.get("action") == "user_text_input":
                        text = data.get("text", "")
                        if text:
                            # Forward text command to the daemon asynchronously
                            asyncio.create_task(forward_text_to_daemon(text))
                except Exception as e:
                    logger.debug(f"Error handling ws text input: {e}")
    finally:
        await ws_manager.unregister(ws)
        
    return ws

async def system_metrics_loop() -> None:
    """Background task to broadcast hardware metrics if clients are connected."""
    while True:
        try:
            if ws_manager.active_connections:
                cpu = psutil.cpu_percent(interval=None)
                mem = psutil.virtual_memory()
                disk = psutil.disk_usage('/')
                
                # Check browser process state
                from nova.browser_manager import BrowserManager
                browser_active = BrowserManager.is_browser_running()
                
                metrics = {
                    "cpu": cpu,
                    "memory": mem.percent,
                    "disk": disk.percent,
                    "browser_active": browser_active
                }
                
                # Broadcast using event bus emit
                from nova.dashboard.event_bus import emit
                emit("system_metrics", module="diagnostics", status="success", metadata=metrics)
        except Exception as e:
            logger.debug(f"Metrics task error: {e}")
            
        await asyncio.sleep(2.0)

async def health_check_loop() -> None:
    """Background task to broadcast voice state health status changes."""
    last_report = None
    while True:
        try:
            if ws_manager.active_connections:
                from nova.voice.conversation import get_voice_status_report
                report = get_voice_status_report()
                if report != last_report:
                    last_report = report
                    # Broadcast using event bus emit
                    from nova.dashboard.event_bus import emit
                    emit("health_status", module="core", status="success", metadata=report)
        except Exception as e:
            logger.debug(f"Health check task error: {e}")
            
        await asyncio.sleep(4.0)

async def start_server(port: int = 11436) -> None:
    """Run the main server lifecycle loop (bind, route, run)."""
    global _active_loop, _runner
    _active_loop = asyncio.get_running_loop()
    
    register_dashboard_context(_active_loop, ws_manager)
    
    app = web.Application()
    app.router.add_get("/", index_handler)
    app.router.add_get("/ws", ws_handler)
    app.router.add_static("/assets/", path=STATIC_DIR, name="assets")
    
    _runner = web.AppRunner(app)
    await _runner.setup()
    site = web.TCPSite(_runner, "127.0.0.1", port)
    
    try:
        await site.start()
        logger.info(f"Dashboard server successfully bound to 127.0.0.1:{port}")
    except Exception as e:
        logger.error(f"Failed to start dashboard HTTP server on port {port}: {e}")
        unregister_dashboard_context()
        return

    # Start background polling tasks
    metrics_task = asyncio.create_task(system_metrics_loop())
    health_task = asyncio.create_task(health_check_loop())
    
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        logger.info("Dashboard server shutdown signal received.")
    finally:
        metrics_task.cancel()
        health_task.cancel()
        
        # Close all active websocket clients
        for ws in list(ws_manager.active_connections):
            try:
                await ws.close(code=1001, message="Server shutting down")
            except Exception:
                pass
            
        await _runner.cleanup()
        unregister_dashboard_context()

def stop_server() -> None:
    """Trigger graceful server shutdown by cancelling start_server task."""
    global _active_loop
    if _active_loop and _active_loop.is_running():
        for task in asyncio.all_tasks(_active_loop):
            # Check if task is running start_server coro
            if "start_server" in str(task.get_coro()):
                _active_loop.call_soon_threadsafe(task.cancel)
