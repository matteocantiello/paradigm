"""Real-data mandate D1: provenance classifier + policy gate + prompt directive."""

from __future__ import annotations

from paradigm.config import Config
from paradigm.orchestrator.constants import data_policy_directive
from paradigm.orchestrator.data_provenance import (
    DERIVED,
    REAL,
    RESAMPLED,
    SYNTHETIC,
    classify_data_provenance,
    excluded_by_policy,
)

# --- classifier --------------------------------------------------------------


def test_loading_real_data_is_real():
    code = (
        "import pandas as pd\ndf = pd.read_csv('/data/shared/data/tablee1.dat')\nprint(df.corr())"
    )
    verdict, reasons = classify_data_provenance(code)
    assert verdict == REAL and reasons


def test_bootstrap_over_loaded_data_is_resampled():
    code = (
        "df = pd.read_csv('/data/shared/data/cat.csv')\n"
        "rng = np.random.default_rng(0)\n"
        "for _ in range(1000):\n"
        "    sample = df.sample(frac=1, replace=True, random_state=rng.integers(1e9))\n"
    )
    assert classify_data_provenance(code)[0] == RESAMPLED


def test_pure_theory_is_derived():
    code = "import numpy as np\nteff = np.linspace(3.5, 4.7, 100)\nlum = 4 * teff - 10.61\nprint(lum.mean())"
    assert classify_data_provenance(code)[0] == DERIVED


def test_random_generation_without_inputs_is_synthetic():
    # The 'MIST-like tracks' incident: fabricated stand-in data, no file loads.
    code = (
        "import numpy as np\n"
        "# generate synthetic MIST-like evolutionary tracks\n"
        "logg = np.random.uniform(1.0, 4.5, 500)\n"
        "xi = 2.0 + 3.0 * np.random.normal(size=500)\n"
        "np.savetxt('tracks.csv', np.c_[logg, xi])\n"
    )
    verdict, reasons = classify_data_provenance(code)
    assert verdict == SYNTHETIC
    assert any("without loading" in r for r in reasons)


def test_labeled_synthetic_component_alongside_real_data_is_synthetic():
    code = (
        "df = pd.read_csv('/data/shared/data/cat.csv')\n"
        "# augment with a mock catalog for the sparse regime\n"
        "extra = np.random.normal(size=(100, 2))\n"
    )
    assert classify_data_provenance(code)[0] == SYNTHETIC


def test_marker_in_stdout_counts():
    code = "x = np.random.normal(size=100)\nprint('built dataset')\n"
    verdict, _ = classify_data_provenance(code, stdout="using synthetic sample of 100 stars")
    assert verdict == SYNTHETIC


# --- policy gate --------------------------------------------------------------


def test_excluded_only_under_real_only():
    assert excluded_by_policy(SYNTHETIC, "real_only") is True
    assert excluded_by_policy(SYNTHETIC, "prefer_real") is False
    assert excluded_by_policy(SYNTHETIC, "permissive") is False
    assert excluded_by_policy(RESAMPLED, "real_only") is False
    assert excluded_by_policy(REAL, "real_only") is False


# --- prompt directive + config ------------------------------------------------


def test_directives_exist_for_active_policies():
    assert "FORBIDDEN" in data_policy_directive("real_only")
    assert "DATA UNAVAILABLE" in data_policy_directive("real_only")
    # The carve-outs must survive edits — banning statistics would be a bug.
    assert "bootstrap" in data_policy_directive("real_only")
    assert "LABEL" in data_policy_directive("prefer_real")
    assert data_policy_directive("permissive") == ""


def test_config_default_and_yaml(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    assert Config().orchestrator.data_policy == "prefer_real"
    from paradigm.config import load_config

    assert load_config("configs/production.yaml").orchestrator.data_policy == "real_only"
    assert load_config("configs/open.yaml").orchestrator.data_policy == "real_only"
