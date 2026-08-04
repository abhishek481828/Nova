# Nova v3.0 — Architecture Audit Report & System Blueprint

## Executive Summary
Nova v3.0 is a modular, production-grade AI mobile platform designed for continuous offline execution, local intent processing, hybrid laptop/mobile task orchestration, structured personal memory, smart automation, multi-device synchronization, and an extensible AI skills framework.

---

## Subsystem Architecture Audit

### 1. Mobile Foundation & Lifecycle (`mobile/core/`, `mobile/lifecycle/`)
- **Role**: Entry point and central coordinator (`MobileCoreManager`).
- **Audit Result**: Clean event bus interface (`LifecycleManager`). Supervised coroutine scope prevents app-wide crashes when child tasks fail. Zero tight coupling to specific plugin implementations.

### 2. Offline Wake Word Engine (`mobile/wakeword/`)
- **Role**: Continuous background detection of wake word ("Hey Nova").
- **Audit Result**: Energy-efficient sliding window frame scoring with energy threshold filtering (> 0.01 RMS) to prevent CPU wakeups during silence. Foreground Service lifecycle bound.

### 3. Voice Pipeline (`mobile/voice/`)
- **Role**: Immediate post-wakeword audio capture, state machine (`IDLE` → `RECORDING` → `PROCESSING` → `RESPONDING`), and speech-to-text conversion.
- **Audit Result**: Auto-cancel timeout (5.0s max session) prevents microphone leaks. Integrates cleanly with CommandEngine and SkillExecutor.

### 4. Local Command Engine (`mobile/command/`)
- **Role**: Resolves user voice text to intent (`BuiltInIntent`), extracts entity parameters, validates security rules, and dispatches to system plugins.
- **Audit Result**: 25+ built-in intents. Instant local execution (< 15ms latency).

### 5. Hybrid AI Router (`mobile/hybrid/`)
- **Role**: Intelligently routes execution between Local Android vs. Nova Core Laptop based on device connectivity, capability matching, and user policy.
- **Audit Result**: Auto-probing device discovery with automatic fallback to local execution if Nova Core is offline.

### 6. Personal Memory System (`mobile/memory/`)
- **Role**: Structured personal information, habits, contacts, favorite apps, and recent commands.
- **Audit Result**: NO vector store / LLM memory. Plain structured entries with sensitive key blocking (passwords, tokens, OTPs are rejected on store).

### 7. Smart Automation & Routine Engine (`mobile/automation/`)
- **Role**: User-created routine definitions driven by 16 trigger types and pre-conditions.
- **Audit Result**: Explicit user creation only. Nova NEVER invents routines automatically. Global `pauseAll()` safety switch.

### 8. Multi-Device Synchronization (`mobile/sync/`)
- **Role**: Seamless state sync between Phone and Nova Core laptop.
- **Audit Result**: Only authenticated devices allowed. SHA-256 payload integrity checksum. Offline queue with 500-item cap. Sensitive keys strictly blocked.

### 9. AI Skills Framework (`mobile/skills/`)
- **Role**: Dynamic skill loading, sandboxed execution (`SkillContext`), permissions approval queue, and built-in skill pack (9 first-party skills).
- **Audit Result**: Error-isolated execution. Crashing skills emit spoken error responses without crashing Nova Core.

---

## System Boundaries & Constraints
- **Zero Cloud Dependency**: Operates entirely offline or over local LAN to Nova Core laptop.
- **Zero Local LLM Overhead**: High-speed, rule-and-intent parsing for zero-latency mobile responsiveness.
- **Backward Compatibility**: Fully preserves Nova v2.0 desktop companion contracts.
