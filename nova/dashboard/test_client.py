import asyncio
import json
import websockets

async def test_listen():
    uri = "ws://127.0.0.1:11436/ws"
    print(f"Connecting to {uri}...")
    try:
        async with websockets.connect(uri) as websocket:
            print("Connected! Waiting for events (press Ctrl+C to stop)...")
            while True:
                msg = await websocket.recv()
                try:
                    event = json.loads(msg)
                    print("\nReceived structured event:")
                    print(json.dumps(event, indent=2))
                    
                    # Assert schema keys exist
                    missing_keys = []
                    for key in ("timestamp", "module", "event", "status", "metadata"):
                        if key not in event:
                            missing_keys.append(key)
                    
                    if missing_keys:
                        print(f"  ✗ SCHEMA FAILED: Missing keys: {missing_keys}")
                    else:
                        print("  ✓ SCHEMA PASSED: All structured keys present.")
                except Exception as e:
                    print(f"Failed to parse event: {e}")
    except ConnectionRefusedError:
        print("Connection refused. Is Nova daemon running? Start it with: systemctl --user start nova.service")

if __name__ == "__main__":
    try:
        asyncio.run(test_listen())
    except KeyboardInterrupt:
        print("\nExiting test client.")
