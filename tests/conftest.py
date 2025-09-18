"""Shared fixtures for the retro-trace test suite."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


def pytest_configure(config):
    config.addinivalue_line("markers", "full_data: tests that use the full 3500-case data package")


@pytest.fixture(scope="session")
def repo() -> Path:
    return REPO


@pytest.fixture(scope="session")
def configs(repo) -> tuple[dict, dict]:
    import yaml

    qa = yaml.safe_load(open(repo / "configs" / "qa_labels.yaml", encoding="utf-8"))
    rules = yaml.safe_load(open(repo / "configs" / "label_rules.yaml", encoding="utf-8"))
    return qa, rules


@pytest.fixture(scope="session")
def full_data(tmp_path_factory) -> Path:
    """Full 3500-case data package generated once per test session."""
    from retro_trace.a1 import generator as g

    out = tmp_path_factory.mktemp("full_data")
    tables = g.generate_tables(seed=g.SEED_DEFAULT)
    g.write_tables(tables, out)
    g.write_params(out, g.SEED_DEFAULT, tables)
    return out


@pytest.fixture(scope="session")
def small_data(tmp_path_factory) -> Path:
    """Small (600-case) data package for fast behavioral tests."""
    from retro_trace.a1 import generator as g

    out = tmp_path_factory.mktemp("small_data")
    tables = g.generate_tables(seed=20250711, n_total=600)
    g.write_tables(tables, out)
    g.write_params(out, 20250711, tables)
    return out


@pytest.fixture()
def attribute_run(small_data, tmp_path) -> Path:
    """Run attribution over the small data package."""
    from retro_trace.cli import main

    out = tmp_path / "a1_attribution"
    rc = main(["a1", "attribute", "--input", str(small_data), "--out", str(out)])
    assert rc == 0
    return out


@pytest.fixture(scope="session")
def full_attribute_run(full_data, tmp_path_factory) -> Path:
    """Run attribution over the full data package once per session."""
    from retro_trace.cli import main

    out = tmp_path_factory.mktemp("full_attr")
    rc = main(["a1", "attribute", "--input", str(full_data), "--out", str(out)])
    assert rc == 0
    return out


@pytest.fixture()
def full_evaluation(full_attribute_run, tmp_path) -> dict:
    """Evaluate the full-data attribution run and return metrics."""
    import json

    from retro_trace.cli import main

    out = tmp_path / "a1_evaluation"
    rc = main(["a1", "evaluate", "--run", str(full_attribute_run), "--out", str(out)])
    assert rc == 0
    receipt = json.loads((out / "run_receipt.json").read_text(encoding="utf-8"))
    return {"run": out, "metrics": receipt["metrics"]}
