# Nova v2.0 — Protocol & API Reference

Nova v2.0 uses a bi-directional JSON & Binary WebSocket protocol operating on port `8000` / `8765`.

---

## 1. Frame Types

| Message Type | Description |
| :--- | :--- |
| `handshake` | Initial pairing and version negotiation |
| `command` | Action request sent to companion device |
| `response` | Execution response from companion device |
| `event` | Real-time event published over EventBus |
| `heartbeat` | Health & connection heartbeat message |

---

## 2. Supported Action Categories

### Device Management (Phase I)
- `device.info`: Hardware, model, Android OS version, uptime.
- `device.health`: Health status score, memory %, storage %, battery.
- `device.storage`: Internal storage metrics.
- `device.memory`: RAM metrics.
- `device.cpu`: CPU core count & architecture.
- `device.battery`: Battery level, charging status, temperature.
- `file.list`, `file.upload`, `file.download`, `file.delete`, `file.rename`, `file.move`, `file.copy`: File Manager operations.

### Remote Touch & Accessibility (Phase F & G)
- `screen.capture`: Take PNG/JPEG screenshot.
- `screen.tap`: Perform gesture tap at `(x, y)`.
- `screen.swipe`: Perform touch swipe `(x1, y1 -> x2, y2)`.
- `screen.type`: Remote text typing into active input field.
- `global.home`, `global.back`, `global.recents`: Accessibility global gestures.

### Audio & Voice (Phase H)
- `audio.capture.start` / `stop`: 16 kHz 16-bit Mono PCM mic capture.
- `voice.session.start` / `stop`: Duplex voice session management.
- `audio.play`: Play TTS audio on phone speaker.
