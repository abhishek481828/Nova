# Release Guide

This document maps out packaging, versioning, and branch release procedures.

---

## Semantic Versioning
Nova uses SemVer (`MAJOR.MINOR.PATCH`):
*   **MAJOR**: Breaking changes.
*   **MINOR**: New feature additions.
*   **PATCH**: Backward compatible bug fixes.

---

## Release Process
1.  Verify test suite results are green.
2.  Update version number in `VERSION`.
3.  Add release notes to `CHANGELOG.md` and `RELEASE_NOTES.md`.
4.  Tag and build the release.
