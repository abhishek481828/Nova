# Nova v2.0 — Troubleshooting & FAQ

This document addresses common issues and resolution steps.

---

## 1. Phone Shows "Device not connected via WebSocket or ADB"

### Problem
Commands return `"Unable to read battery level (Device not connected via WebSocket or ADB)"`.

### Solution
1. **Option A (USB Cable)**: Plug your phone into your laptop via USB cable. Enable **USB Debugging** in phone Developer Options. Verify `adb devices` in your terminal displays your device serial.
2. **Option B (Wi-Fi Companion App)**: Open the **Nova Companion** app on your phone and tap **Connect**. Ensure the laptop IP is set correctly (e.g. `http://10.1.185.43:8000`).

---

## 2. Phone Microphone Does Not Record Audio

### Problem
Running `mic on` returns `"Microphone unavailable"`.

### Solution
1. Open phone Settings -> Apps -> Nova Companion -> Permissions.
2. Ensure **Microphone (`RECORD_AUDIO`)** permission is granted.

---

## 3. WhatsApp Call Fails

### Solution
Nova automatically uses the host ADB touch macro for WhatsApp calls to bypass non-system app Android touch restrictions. Ensure USB Debugging is ON.
