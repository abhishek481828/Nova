# Configuration Guide

This guide describes how to configure the Nova assistant.

---

## ⚙️ Environment Configurations (`.env`)
Create `.env` using `.env.example`:
*   `OLLAMA_API_KEY`: API key for custom local setups.
*   `GEMINI_API_KEY`: Fallback reasoning key.
*   `ELEVENLABS_API_KEY`: Voice synthesis authentication.

---

## 🛠️ Framework Template Configurations
Templates keyword matching resides under [mappings.json](../nova/ai/planner/templates/mappings.json). Edit mappings rules to customize matching filters without editing python code.
