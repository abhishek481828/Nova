# Nova Companion — Android Setup & Deployment Guide

This guide details configuring and building the **Nova Companion App** for Android (specifically optimized for Samsung Galaxy A13).

---

## 1. Build Requirements

- OpenJDK 17
- Android SDK (API 34 / Android 14)
- Gradle 8.12

---

## 2. Compiling the APK

Rebuild the companion debug and release APKs:
```bash
nix-shell -p jdk17 --run "export JAVA_HOME=/nix/store/5badkg3gmzg1c29akwglknkizfg6zj0g-openjdk-17.0.17+8 && cd android && ./gradlew assembleDebug assembleRelease"
```

The APKs will be generated in:
- `android/app/build/outputs/apk/debug/app-debug.apk`
- `android/app/build/outputs/apk/release/app-release-unsigned.apk`

---

## 3. Deployment via ADB

1. Enable **Developer Options** and **USB Debugging** on your phone.
2. Connect phone via USB.
3. Install the APK:
   ```bash
   adb install -r android/app/build/outputs/apk/debug/app-debug.apk
   ```
4. Launch the Companion App:
   ```bash
   adb shell am start -n com.nova.companion.debug/com.nova.companion.MainActivity
   ```

---

## 4. Permissions Required

Grant the following permissions in phone Settings:
- Accessibility Service (`NovaAccessibilityService`)
- Microphone (`RECORD_AUDIO`)
- Camera & Storage
- Notification Listener Access
