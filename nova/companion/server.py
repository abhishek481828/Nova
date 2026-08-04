"""Nova Core Companion Gateway Server Runner."""

import uvicorn
from fastapi import FastAPI
from nova.companion.gateway.rest_api import router as companion_router
from nova.companion.gateway.websocket_server import ws_router

app = FastAPI(title="Nova Core v2.0 Gateway", version="2.0.0")
app.include_router(companion_router)
app.include_router(ws_router)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
