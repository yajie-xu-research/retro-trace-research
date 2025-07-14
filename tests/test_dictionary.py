"""Event dictionary: structure, validity windows, pinned hash integrity."""

from __future__ import annotations

import pandas as pd
import pytest

from retro_trace.a1 import dictionary as d


def test_canonical_stages_are_the_seven_frozen_values():
    assert d.CANONICAL_STAGES == (
        "SAMPLE_RECEIVED",
        "ACCESSIONED",
        "LIBRARY_PREPARED",
        "SEQUENCING_STARTED",
        "ANALYSIS_COMPLETE",
        "REVIEWED",
        "RELEASED",
    )


def test_stage_map_covers_all_site_version_combinations(configs):
    df = d.load_dictionary(configs[0])
    combos = set(zip(df["site_key"], df["workflow_version"]))
    expected = {
        (site, version)
        for site in ("SITE_A", "SITE_B", "SITE_C")
        for version in ("WF_V1", "WF_V2", "WF_V3")
    }
    assert combos == expected
    # SITE_A and SITE_B map all seven canonical stages; SITE_C's local event
    # stream lacks the sequencing step, so only six stages are mapped there.
    for (site, version), group in df.groupby(["site_key", "workflow_version"]):
        stages = set(group["canonical_stage"])
        if site == "SITE_C":
            assert stages == set(d.CANONICAL_STAGES) - {"SEQUENCING_STARTED"}
        else:
            assert stages == set(d.CANONICAL_STAGES)


def test_stage_map_validity_windows_are_frozen(configs):
    df = d.load_dictionary(configs[0])
    windows = {}
    for (site, version), group in df.groupby(["site_key", "workflow_version"]):
        windows[(site, version)] = (group["valid_from"].min(), group["valid_to"].max())
    end_wf1 = pd.Timestamp("2024-09-01", tz="UTC")
    boundary_wf2 = (pd.Timestamp("2024-09-01", tz="UTC"), pd.Timestamp("2025-06-01", tz="UTC"))
    start_wf3 = pd.Timestamp("2025-06-01", tz="UTC")
    end_wf3 = pd.Timestamp("2026-06-30", tz="UTC")
    for site in ("SITE_A", "SITE_B", "SITE_C"):
        assert windows[(site, "WF_V1")][1] == end_wf1
        assert windows[(site, "WF_V2")] == boundary_wf2
        assert windows[(site, "WF_V3")][0] == start_wf3
        assert windows[(site, "WF_V3")][1] == end_wf3  # bounded by the era close


def test_pinned_hash_matches_config(configs):
    assert d.compute_pin() == configs[0]["pinned_dictionary"]["sha256"]


def test_tampered_dictionary_raises(configs, tmp_path):
    tampered = tmp_path / "stage_map_tampered.csv"
    original = d.PACKAGED_DICTIONARY.read_bytes()
    tampered.write_bytes(original.replace(b"RCPT", b"RCPX"))
    with pytest.raises(d.DictionaryIntegrityError):
        d.load_dictionary(configs[0], tampered)


def test_map_event_returns_none_for_unmapped_codes(configs):
    df = d.load_dictionary(configs[0])
    code_index = d.build_code_index(df)
    assert d.map_event(code_index, "SITE_A", "WF_V1", "RCPT") == "SAMPLE_RECEIVED"
    assert d.map_event(code_index, "SITE_A", "WF_V1", "NOT_A_CODE") is None
    assert d.map_event(code_index, "SITE_A", "WF_V1", "ANA") is None  # code from a different site
    assert d.map_event(code_index, "SITE_C", "WF_V2", "SEQ") is None  # stage absent at this site
