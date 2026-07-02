# Plugin Guide

This document describes Nova's dynamic plugin loading mechanism.

---

## Overview
Nova loads action plugins dynamically from the `nova/plugins/` directory. This allows developers to distribute packaged features without modifying core modules.

---

## Lifecycle
1.  **Discovery**: At startup, `PluginManager` scans `nova/plugins/` for subclasses of `BasePlugin`.
2.  **Instantiation**: Discovered plugins are loaded and their skills registered.
3.  **Execution**: System router delegates execution prompts to loaded plugins based on task classification.
