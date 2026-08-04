"""Unit tests for Deployment Step 1: Production Readiness Verification."""

import pytest
import os
import asyncio
from nova.companion.config.loader import ConfigLoader, NovaConfig
from nova.companion.logging_config import setup_structured_logging
from nova.companion.deployment.verifier import StartupVerifier, DeploymentVerificationError
from nova.companion.gateway.rest_api import health_status


def test_config_loader_environments():
    # Load development config
    dev_config = ConfigLoader.load_config(env="development", config_dir="config")
    assert dev_config.environment == "development"
    assert dev_config.server.port == 8000
    assert dev_config.security.jwt_access_expire_seconds == 86400

    # Load production config
    prod_config = ConfigLoader.load_config(env="production", config_dir="config")
    assert prod_config.environment == "production"
    assert prod_config.server.host == "0.0.0.0"
    assert prod_config.server.workers == 4


def test_structured_logging_initialization(tmp_path):
    log_file = str(tmp_path / "logs" / "test_backend.log")
    logger = setup_structured_logging(log_file=log_file)
    logger.info("Test log line for deployment verification")

    assert os.path.exists(log_file)
    with open(log_file, 'r', encoding='utf-8') as f:
        content = f.read()
        assert "Test log line for deployment verification" in content


def test_startup_verifier():
    verifier = StartupVerifier(env="development")
    success, config = verifier.verify_all(config_dir="config")

    assert success is True
    assert config.environment == "development"
    assert verifier.checks["Configuration Loaded"] is True
    assert verifier.checks["Database Connected"] is True
    assert verifier.checks["JWT Ready"] is True
    assert verifier.checks["Encryption Ready"] is True
    assert verifier.checks["Plugins Loaded"] is True
    assert verifier.checks["REST API Running"] is True
    assert verifier.checks["WebSocket Running"] is True


@pytest.mark.asyncio
async def test_production_health_endpoint():
    res = await health_status()

    assert res["version"] == "2.0.0"
    assert res["server_status"] == "HEALTHY"
    assert res["database_status"] == "CONNECTED"
    assert res["websocket_status"] == "ACTIVE"
    assert isinstance(res["loaded_plugins"], list)
    assert len(res["loaded_plugins"]) > 0
    assert res["uptime_seconds"] >= 0
    assert "T" in res["timestamp"]
