# Nova v3.0 — Security & Hardening Guide

## Security Architecture

```
                  +-----------------------------------+
                  |         User Voice / UI           |
                  +-----------------------------------+
                                    |
                                    v
                  +-----------------------------------+
                  |    Permissions Sandbox Layer      |
                  |  (User Approval Required for Sensitive) |
                  +-----------------------------------+
                                    |
                                    v
+-----------------------+ +-------------------------+ +------------------------+
|   Skill Execution     | |    Command Processing   | |    Sync Engine         |
| (Sandbox Context API) | | (Validated Intent Map) | | (Sensitive Key Block)  |
+-----------------------+ +-------------------------+ +------------------------+
```

---

## Hardening Mechanisms

### 1. Sensitive Data Sync Blocking
The Sync Engine explicitly inspects every key before packaging or applying payloads. The following key patterns are **permanently blocked** from multi-device synchronization:
- `password`, `passwd`, `login_token`, `auth_token`, `access_token`, `refresh_token`, `secret`, `private_key`, `pin`, `cvv`, `ssn`.

### 2. Device Authentication & Trust
- Only devices explicitly registered and marked `isAuthenticated = true` in the `DeviceRegistry` can exchange sync payloads.
- Payloads from unknown or unauthenticated device IDs are dropped immediately.

### 3. Payload Integrity Verification
- Outbound payloads generate a 16-character SHA-256 checksum of their string content.
- Inbound payloads verify checksum match before updating local state.

### 4. Skill Permission Sandboxing
Skills request permissions via `SkillManifest`. Permissions requiring user approval (`CAMERA`, `CONTACTS`, `SMS`, `LOCATION`, `MICROPHONE`, `ACCESSIBILITY`) are held in a pending queue until explicitly approved via `SkillManager.approvePermission()`.

### 5. Destructive Action Safeguards
Destructive plugin operations (e.g. system wipe, file deletion, setting changes) require explicit voice confirmation. Automations cannot execute unconfirmed destructive actions automatically.
