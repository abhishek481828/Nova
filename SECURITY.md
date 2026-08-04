# Nova v2.0 — Security Policy & Security Audit

Nova v2.0 implements end-to-end security safeguards for distributed remote device control.

---

## 1. Security Architecture Summary

1. **Authentication & Authorization**:
   - JWT Access Tokens issued upon successful PIN pairing.
   - Per-device UUID pairing verification.

2. **Encryption & Key Exchange**:
   - ECDH (Elliptic Curve Diffie-Hellman) key agreement.
   - AES-256-GCM authenticated payload encryption.
   - Android KeyStore secret storage for tokens.

3. **ADB Command Guard (`adb_guard.py`)**:
   - Command validation preventing destructive shell executions (`rm -rf /`, `mkfs`, `format`, unauthorized su escalation).
   - Shell argument sanitization escaping dangerous metacharacters (`;&|$`).
   - Audit logging recording every privileged execution with timestamp and duration.

---

## 2. Reporting Security Vulnerabilities

Please report security issues directly to the maintainers or create a security advisory.
