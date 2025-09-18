"""Input data validation checks.

validate runs a battery of structural and integrity checks over the data
package and the frozen dictionary, and writes a per-check report. Rows that
fail hard checks are listed in excluded_rows.csv. Unmapped raw event codes
(legacy feed noise, about 1% of rows) are registered and listed rather than
treated as failures unless they exceed the tolerance.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import yaml

from ..common.hashing import sha256_file
from .dictionary import (
    CANONICAL_STAGES,
    OPEN_VALID_TO,
    PACKAGED_DICTIONARY,
    build_code_index,
    compute_pin,
    load_dictionary,
    map_event,
)

UNMAPPED_TOLERANCE = 0.02

EVENTS_COLUMNS = [
    "case_key",
    "event_code_raw",
    "occurred_at_utc",
    "known_at_utc",
    "source_system",
    "record_version",
]
QUALITY_COLUMNS = [
    "event_id",
    "case_key",
    "event_type",
    "rule_version",
    "adjudicated_at",
    "adjudicated_by",
    "basis",
]
SAMPLE_CLASS_COLUMNS = ["class_id", "test_family", "priority_class", "source_category", "valid_from", "valid_to"]
LOAD_STAFFING_COLUMNS = [
    "site_key",
    "workflow_version",
    "snapshot_at_utc",
    "queue_size",
    "staffing_category",
    "equipment_class",
]
CASES_COLUMNS = [
    "case_key",
    "site_key",
    "workflow_version",
    "test_family",
    "priority_class",
    "source_category",
    "sample_class",
    "received_at_utc",
    "released_at_utc",
    "is_released",
]


def validate_package(data_dir: str | Path, config: dict, label_rules: dict) -> dict:
    data = Path(data_dir)
    checks = []
    excluded_rows = []

    def check(check_id: str, table: str, ok: bool, detail: str, n_rows: int = 0):
        checks.append(
            {
                "check_id": check_id,
                "table": table,
                "status": "PASS" if ok else "FAIL",
                "detail": detail,
                "n_rows_affected": n_rows,
            }
        )

    # --- dictionary integrity ---
    pin_ok = True
    pin_msg = "pinned hash matches the frozen dictionary"
    try:
        load_dictionary(config, PACKAGED_DICTIONARY)
    except Exception as exc:  # noqa: BLE001 - report any integrity failure
        pin_ok = False
        pin_msg = f"dictionary integrity failure: {exc}"
    check("DICT_PIN", "dictionary", pin_ok, pin_msg)

    data_stage_map = data / "stage_map.csv"
    if data_stage_map.exists():
        same = sha256_file(data_stage_map) == sha256_file(PACKAGED_DICTIONARY)
        check(
            "DICT_COPY_BYTES",
            "dictionary",
            same,
            "data stage_map.csv is a byte copy of the frozen dictionary"
            if same
            else "data stage_map.csv differs from the frozen dictionary",
        )
    else:
        check("DICT_COPY_BYTES", "dictionary", False, "stage_map.csv missing from data package")

    # --- schema checks ---
    for table, cols in (
        ("events.csv", EVENTS_COLUMNS),
        ("quality_events.csv", QUALITY_COLUMNS),
        ("sample_classes.csv", SAMPLE_CLASS_COLUMNS),
        ("load_staffing.csv", LOAD_STAFFING_COLUMNS),
        ("cases.csv", CASES_COLUMNS),
    ):
        path = data / table
        if not path.exists():
            check(f"SCHEMA_{table}", table, False, f"missing table {table}")
            continue
        df = pd.read_csv(path, dtype=str)
        missing = [c for c in cols if c not in df.columns]
        check(
            f"SCHEMA_{table}",
            table,
            not missing,
            f"required columns present" if not missing else f"missing columns: {missing}",
            len(df),
        )

    # --- deeper checks (only when the schema passed) ---
    events_path = data / "events.csv"
    cases_path = data / "cases.csv"
    if not events_path.exists() or not cases_path.exists():
        return {"checks": checks, "excluded_rows": excluded_rows}

    events = pd.read_csv(events_path, dtype=str)
    cases = pd.read_csv(cases_path, dtype=str)
    events["occurred_at_utc"] = pd.to_datetime(events["occurred_at_utc"], format="ISO8601", utc=True)
    events["known_at_utc"] = pd.to_datetime(events["known_at_utc"], format="ISO8601", utc=True)
    cases["received_at_utc"] = pd.to_datetime(cases["received_at_utc"], format="ISO8601", utc=True)
    cases["released_at_utc"] = pd.to_datetime(cases["released_at_utc"], format="ISO8601", utc=True)

    stage_map = load_dictionary(config, PACKAGED_DICTIONARY)
    code_index = build_code_index(stage_map)
    combo = cases.set_index("case_key")[["site_key", "workflow_version"]]

    # unmapped codes (registered, tolerated below threshold)
    unmapped = []
    for _, ev in events.iterrows():
        c = tuple(combo.loc[ev["case_key"]])
        if map_event(code_index, c[0], c[1], ev["event_code_raw"]) is None:
            unmapped.append(
                {
                    "case_key": ev["case_key"],
                    "event_code_raw": ev["event_code_raw"],
                    "occurred_at_utc": ev["occurred_at_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reason": "UNMAPPED_EVENT_CODE",
                }
            )
    rate = len(unmapped) / len(events) if len(events) else 0.0
    check(
        "EVENTS_UNMAPPED",
        "events.csv",
        rate <= UNMAPPED_TOLERANCE,
        f"{len(unmapped)} unmapped event rows ({rate:.4%}); tolerance {UNMAPPED_TOLERANCE:.0%}",
        len(unmapped),
    )
    excluded_rows.extend(unmapped)

    # workflow-version validity applies to the case receipt: a case received
    # while a workflow version was active keeps that version for its whole
    # process, even if later events cross the version boundary date.
    windows: dict[tuple[str, str], tuple[pd.Timestamp, pd.Timestamp]] = {}
    for (site, version), group in stage_map.groupby(["site_key", "workflow_version"]):
        lo = group["valid_from"].min()
        hi = group["valid_to"].max()
        windows[(site, version)] = (lo, hi if hi < OPEN_VALID_TO else pd.Timestamp("2026-06-30", tz="UTC"))
    out_of_window = 0
    for _, case_row in cases.iterrows():
        c = (case_row["site_key"], case_row["workflow_version"])
        lo, hi = windows.get(c, (None, None))
        if lo is None:
            continue
        if not (lo <= case_row["received_at_utc"] <= hi):
            out_of_window += 1
            excluded_rows.append(
                {
                    "case_key": case_row["case_key"],
                    "event_code_raw": "",
                    "occurred_at_utc": case_row["received_at_utc"].strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "reason": "OUT_OF_VERSION_WINDOW",
                }
            )
    check(
        "EVENTS_TIME_WINDOW",
        "cases.csv",
        out_of_window == 0,
        f"{out_of_window} cases received outside their workflow-version validity window",
        out_of_window,
    )

    # known_at >= occurred_at
    bad_known = int((events["known_at_utc"] < events["occurred_at_utc"]).sum())
    check(
        "EVENTS_KNOWN_AFTER_OCCURRED",
        "events.csv",
        bad_known == 0,
        f"{bad_known} rows where known_at precedes occurred_at",
        bad_known,
    )

    # stage coverage per case, measured against the stages the frozen
    # dictionary maps for the case's own site and workflow version (a site
    # whose local stream lacks a step is not required to emit it).
    mapped = events.merge(combo.reset_index(), on="case_key")
    mapped["canonical_stage"] = [
        map_event(code_index, r.site_key, r.workflow_version, r.event_code_raw)
        for r in mapped.itertuples()
    ]
    expected_by_combo = {
        (site, version): group["canonical_stage"].nunique()
        for (site, version), group in stage_map.groupby(["site_key", "workflow_version"])
    }
    coverage = mapped.groupby("case_key")["canonical_stage"].nunique()
    combo_of_case = combo.reset_index().set_index("case_key")
    incomplete = 0
    for case_key, n_covered in coverage.items():
        expected = expected_by_combo.get(tuple(combo_of_case.loc[case_key]))
        if expected is not None and n_covered < expected:
            incomplete += 1
    check(
        "EVENTS_STAGE_COVERAGE",
        "events.csv",
        incomplete == 0,
        f"{incomplete} cases missing at least one stage mapped for their site and workflow version",
        incomplete,
    )

    # quality events
    quality_path = data / "quality_events.csv"
    if quality_path.exists():
        qe = pd.read_csv(quality_path, dtype=str)
        bad_type = int((~qe["event_type"].isin(["DELAY", "REWORK"])).sum())
        check(
            "QUALITY_EVENT_TYPE",
            "quality_events.csv",
            bad_type == 0,
            f"{bad_type} rows with event_type outside DELAY/REWORK",
            bad_type,
        )
        known_cases = set(cases["case_key"])
        unknown_case = int((~qe["case_key"].isin(known_cases)).sum())
        check(
            "QUALITY_CASE_KEY",
            "quality_events.csv",
            unknown_case == 0,
            f"{unknown_case} rows referencing unknown case keys",
            unknown_case,
        )
        rule_ok = qe["rule_version"].eq(label_rules["rule_version"])
        check(
            "QUALITY_RULE_VERSION",
            "quality_events.csv",
            bool(rule_ok.all()),
            f"rule_version consistent with label rules ({label_rules['rule_version']})"
            if rule_ok.all()
            else f"rule_version mismatch, expected {label_rules['rule_version']}",
            int((~rule_ok).sum()),
        )
        check(
            "QUALITY_BASIS_PRESENT",
            "quality_events.csv",
            bool(qe["basis"].notna().all()) and bool((qe["basis"].str.len() > 0).all()),
            "every label carries a basis",
        )

    # sample classes
    sc = pd.read_csv(data / "sample_classes.csv", dtype=str)
    dup_class = int(sc["class_id"].duplicated().sum())
    check("CLASS_UNIQUE_ID", "sample_classes.csv", dup_class == 0, f"{dup_class} duplicate class ids", dup_class)
    unknown_class = int((~cases["sample_class"].isin(set(sc["class_id"]))).sum())
    check(
        "CLASS_REGISTRY_COVERAGE",
        "cases.csv",
        unknown_class == 0,
        f"{unknown_class} cases referencing undefined sample classes",
        unknown_class,
    )

    # load staffing
    ls = pd.read_csv(data / "load_staffing.csv", dtype=str)
    valid_sites = {"SITE_A", "SITE_B", "SITE_C"}
    valid_versions = {"WF_V1", "WF_V2", "WF_V3"}
    bad_site = int((~ls["site_key"].isin(valid_sites)).sum())
    bad_version = int((~ls["workflow_version"].isin(valid_versions)).sum())
    bad_staffing = int((~ls["staffing_category"].isin(["FULL", "REDUCED", "CRITICAL"])).sum())
    bad_equipment = int((~ls["equipment_class"].isin(["PRIMARY", "FALLBACK"])).sum())
    check(
        "LOAD_STAFFING_ENUMS",
        "load_staffing.csv",
        bad_site + bad_version + bad_staffing + bad_equipment == 0,
        f"enum violations: site {bad_site}, version {bad_version}, staffing {bad_staffing}, equipment {bad_equipment}",
        bad_site + bad_version + bad_staffing + bad_equipment,
    )

    # case registry plausibility
    bad_order = int((cases["released_at_utc"] <= cases["received_at_utc"]).sum())
    bad_released = int((~cases["is_released"].isin(["0", "1"])).sum())
    check(
        "CASES_PLAUSIBILITY",
        "cases.csv",
        bad_order == 0 and bad_released == 0,
        f"{bad_order} cases with released_at <= received_at; {bad_released} invalid is_released",
        bad_order + bad_released,
    )

    return {"checks": checks, "excluded_rows": excluded_rows}
