"""Tests for configuration management."""

import os
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
import yaml

from paradigm.config import Config, load_config


def test_default_config():
    """Test default configuration values."""
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    config = Config()

    assert config.agent.default_model == "claude-sonnet-4-5-20250929"
    assert config.agent.max_tokens == 8192
    assert config.sandbox.enabled is True
    assert config.sandbox.network_mode == "none"
    assert config.api_key == "test-key"


def test_config_validation():
    """Test configuration validation."""
    # Missing API key should raise error
    if "ANTHROPIC_API_KEY" in os.environ:
        del os.environ["ANTHROPIC_API_KEY"]

    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        Config()


def test_load_config_from_yaml():
    """Test loading configuration from YAML file."""
    os.environ["ANTHROPIC_API_KEY"] = "test-key"

    with TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test_config.yaml"

        # Write test config
        config_data = {
            "agent": {
                "max_tokens": 2048,
                "temperature": 0.5,
            },
            "sandbox": {
                "enabled": False,
            },
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        # Load config
        config = load_config(config_path)

        assert config.agent.max_tokens == 2048
        assert config.agent.temperature == 0.5
        assert config.sandbox.enabled is False


def test_storage_config_creates_directory():
    """Test that storage config creates data directory."""
    os.environ["ANTHROPIC_API_KEY"] = "test-key"

    with TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir).resolve() / "test_data"
        assert not data_dir.exists()

        config = Config(storage={"data_dir": str(data_dir)})

        assert data_dir.exists()
        assert config.storage.db_path == data_dir / "paradigm.db"
        assert config.storage.log_path == data_dir / "events.jsonl"


def test_env_var_override():
    """Test environment variable override."""
    os.environ["ANTHROPIC_API_KEY"] = "test-key"

    with TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir).resolve() / "env_data"
        os.environ["PARADIGM_DATA_DIR"] = str(data_dir)

        config = load_config()

        assert config.storage.data_dir == data_dir
        assert data_dir.exists()

        # Cleanup
        del os.environ["PARADIGM_DATA_DIR"]
