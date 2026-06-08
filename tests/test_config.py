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


def test_citation_config_defaults():
    """Test CitationConfig default values."""
    os.environ["ANTHROPIC_API_KEY"] = "test-key"
    config = Config()

    assert config.citation.enable_citation_grounding is False
    assert config.citation.perplexity_api_key_env == "PERPLEXITY_API_KEY"
    assert config.citation.citation_sections == [
        "introduction",
        "methods",
        "results",
        "discussion",
        "conclusion",
    ]
    assert config.citation.max_retries_per_paragraph == 3
    assert config.citation.perplexity_timeout == 120.0
    assert config.citation.enable_novelty_check is False
    assert config.citation.novelty_mode == "semantic_scholar"
    assert config.citation.futurehouse_api_key_env == "FUTURE_HOUSE_API_KEY"
    assert config.citation.novelty_max_iterations == 5


def test_citation_config_from_yaml():
    """Test loading CitationConfig from YAML."""
    os.environ["ANTHROPIC_API_KEY"] = "test-key"

    with TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "test_config.yaml"

        config_data = {
            "citation": {
                "enable_citation_grounding": True,
                "citation_sections": ["introduction", "methods", "discussion"],
                "perplexity_timeout": 60.0,
                "enable_novelty_check": True,
                "novelty_mode": "futurehouse",
            },
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        config = load_config(config_path)

        assert config.citation.enable_citation_grounding is True
        assert config.citation.citation_sections == ["introduction", "methods", "discussion"]
        assert config.citation.perplexity_timeout == 60.0
        assert config.citation.enable_novelty_check is True
        assert config.citation.novelty_mode == "futurehouse"
