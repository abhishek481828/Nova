"""Centralized Configuration Loader for Nova v2.0."""

import os
import re
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


class ServerConfig(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8000
    workers: int = 1


class SecurityConfig(BaseModel):
    jwt_secret_key: str = "dev_nova_v2_secret_key_change_in_production"
    jwt_access_expire_seconds: int = 86400
    jwt_refresh_expire_seconds: int = 2592000
    pairing_pin_ttl_seconds: int = 300


class TransportConfig(BaseModel):
    heartbeat_interval_seconds: int = 15
    reconnect_timeout_seconds: int = 45
    max_upload_size_bytes: int = 52428800


class StorageConfig(BaseModel):
    database_path: str = "~/.nova/companion_v2.db"
    log_directory: str = "logs"
    media_directory: str = "~/.nova/media"


class NovaConfig(BaseModel):
    environment: str = "development"
    debug: bool = True
    server: ServerConfig = Field(default_factory=ServerConfig)
    security: SecurityConfig = Field(default_factory=SecurityConfig)
    transport: TransportConfig = Field(default_factory=TransportConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)


def parse_simple_yaml(text: str) -> Dict[str, Any]:
    """Lightweight fallback YAML parser if PyYAML package is missing."""
    result: Dict[str, Any] = {}
    current_section = None

    for line in text.splitlines():
        line = line.split('#')[0].strip()
        if not line:
            continue

        if ':' in line:
            parts = line.split(':', 1)
            key = parts[0].strip()
            val_str = parts[1].strip()

            if not val_str:
                current_section = key
                result[current_section] = {}
            else:
                # Parse value
                val: Any = val_str
                if val_str.lower() == 'true':
                    val = True
                elif val_str.lower() == 'false':
                    val = False
                elif val_str.isdigit():
                    val = int(val_str)
                elif val_str.startswith('"') and val_str.endswith('"'):
                    val = val_str[1:-1]
                elif val_str.startswith("'") and val_str.endswith("'"):
                    val = val_str[1:-1]

                if current_section and isinstance(result.get(current_section), dict):
                    result[current_section][key] = val
                else:
                    result[key] = val

    return result


class ConfigLoader:
    _instance: Optional[NovaConfig] = None

    @classmethod
    def load_config(cls, env: str = "development", config_dir: str = "config") -> NovaConfig:
        filename = f"{env}.yaml"
        file_path = os.path.join(config_dir, filename)

        if not os.path.exists(file_path):
            # Try workspace root search
            alt_path = os.path.join(os.getcwd(), config_dir, filename)
            if os.path.exists(alt_path):
                file_path = alt_path

        data: Dict[str, Any] = {}
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                if HAS_YAML:
                    data = yaml.safe_load(content) or {}
                else:
                    data = parse_simple_yaml(content)

        config = NovaConfig(**data) if data else NovaConfig(environment=env)

        # Create required storage and log directories automatically
        db_expanded = os.path.expanduser(config.storage.database_path)
        os.makedirs(os.path.dirname(db_expanded), exist_ok=True)

        log_dir_expanded = os.path.expanduser(config.storage.log_directory)
        os.makedirs(log_dir_expanded, exist_ok=True)

        media_dir_expanded = os.path.expanduser(config.storage.media_directory)
        os.makedirs(media_dir_expanded, exist_ok=True)

        cls._instance = config
        return config

    @classmethod
    def get_config(cls) -> NovaConfig:
        if cls._instance is None:
            return cls.load_config()
        return cls._instance
