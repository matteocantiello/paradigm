"""Tests for the backend-local config loader.

The key contract (VM incident, 2026-06-30): a config file that EXISTS but
fails to parse/validate must abort startup loudly — never silently fall back
to a default config whose empty data dir makes papers/cycles appear to vanish.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.api.config import BackendConfig, ConfigParseError, load_backend_config
from backend.api.main import _load_paradigm_config

CONFLICT_MARKED_YAML = """\
storage:
<<<<<<< HEAD
  data_dir: ./data
=======
  data_dir: /var/lib/paradigm/data
>>>>>>> main
"""


def _write(tmp_path: Path, content: str) -> Path:
    config_path = tmp_path / "configs" / "production.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(content)
    return config_path


def test_valid_config_loads(tmp_path: Path) -> None:
    data_dir = tmp_path / "mydata"
    config_path = _write(
        tmp_path,
        f"storage:\n  data_dir: {data_dir}\nagent:\n  default_model: test-model\n",
    )
    cfg = load_backend_config(config_path)
    assert cfg.agent.default_model == "test-model"
    assert cfg.storage.data_dir == data_dir.resolve()


def test_unresolved_merge_conflict_markers_are_fatal(tmp_path: Path) -> None:
    config_path = _write(tmp_path, CONFLICT_MARKED_YAML)
    with pytest.raises(ConfigParseError, match="production.yaml"):
        load_backend_config(config_path)


def test_non_mapping_yaml_is_fatal(tmp_path: Path) -> None:
    config_path = _write(tmp_path, "- just\n- a list\n")
    with pytest.raises(ConfigParseError, match="mapping"):
        load_backend_config(config_path)


def test_validation_failure_is_fatal(tmp_path: Path) -> None:
    # agent.overrides must be a mapping of role -> override dicts
    config_path = _write(
        tmp_path,
        "agent:\n  overrides:\n    theorist:\n      max_tokens: not-an-int\n",
    )
    with pytest.raises(ConfigParseError, match="production.yaml"):
        load_backend_config(config_path)


def test_missing_default_yaml_keeps_quiet_default(tmp_path: Path) -> None:
    cfg = load_backend_config(tmp_path / "default.yaml")
    assert isinstance(cfg, BackendConfig)


def test_missing_explicit_config_raises_file_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_backend_config(tmp_path / "nope.yaml")


def test_lifespan_loader_is_fatal_on_broken_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The startup path must propagate the parse failure, not return a fallback."""
    config_path = _write(tmp_path, CONFLICT_MARKED_YAML)
    monkeypatch.setenv("PARADIGM_CONFIG", str(config_path))
    with pytest.raises(ConfigParseError, match="production.yaml"):
        _load_paradigm_config()


def test_lifespan_loader_returns_none_when_file_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PARADIGM_CONFIG", str(tmp_path / "missing.yaml"))
    assert _load_paradigm_config() is None
