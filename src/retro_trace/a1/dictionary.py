"""Frozen event dictionary with pinned-hash integrity check.

The seven canonical stages and the site-by-workflow-version raw event code
mapping are a frozen copy of the STAR-TAT event dictionary v1.0. The pin hash
recorded in configs/qa_labels.yaml covers the dictionary CSV bytes plus the
canonical stage list; any tampering aborts the pipeline at load time.

Step 1 of the pipeline uses this dictionary to unify stages; event rows whose
raw codes cannot be mapped are registered in the non-comparable ledger and
excluded from stage-duration computation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from ..common.hashing import dictionary_pin

CANONICAL_STAGES: tuple[str, ...] = (
    "SAMPLE_RECEIVED",
    "ACCESSIONED",
    "LIBRARY_PREPARED",
    "SEQUENCING_STARTED",
    "ANALYSIS_COMPLETE",
    "REVIEWED",
    "RELEASED",
)

PACKAGED_DICTIONARY = Path(__file__).resolve().parent / "data" / "stage_map_v1_0.csv"

STAGE_MAP_COLUMNS = [
    "site_key",
    "workflow_version",
    "event_code_raw",
    "canonical_stage",
    "valid_from",
    "valid_to",
    "reviewed_by",
]

OPEN_VALID_TO = pd.Timestamp.max.tz_localize("UTC")  # internal sentinel for open-ended validity


class DictionaryIntegrityError(RuntimeError):
    """Raised when the pinned dictionary hash does not match the file."""


def compute_pin(dictionary_path: str | Path = PACKAGED_DICTIONARY) -> str:
    return dictionary_pin(dictionary_path, CANONICAL_STAGES)


def load_dictionary(
    config: dict,
    dictionary_path: str | Path = PACKAGED_DICTIONARY,
) -> pd.DataFrame:
    """Load the frozen dictionary and verify the pinned hash from the config."""
    expected = config.get("pinned_dictionary", {}).get("sha256")
    actual = compute_pin(dictionary_path)
    if expected != actual:
        raise DictionaryIntegrityError(
            f"dictionary pin mismatch: config {expected!r} != computed {actual!r}"
        )
    df = pd.read_csv(dictionary_path, dtype=str)
    df["valid_from"] = pd.to_datetime(df["valid_from"], utc=True)
    df["valid_to"] = pd.to_datetime(
        df["valid_to"].replace({"": None}), utc=True
    ).fillna(OPEN_VALID_TO)
    return df


def build_code_index(stage_map: pd.DataFrame) -> dict[tuple[str, str], dict[str, str]]:
    index: dict[tuple[str, str], dict[str, str]] = {}
    for _, row in stage_map.iterrows():
        key = (row["site_key"], row["workflow_version"])
        index.setdefault(key, {})[row["event_code_raw"]] = row["canonical_stage"]
    return index


def map_event(
    code_index: dict[tuple[str, str], dict[str, str]],
    site_key: str,
    workflow_version: str,
    event_code_raw: str,
) -> str | None:
    """Map a raw event code to a canonical stage; None when unmapped."""
    return code_index.get((site_key, workflow_version), {}).get(event_code_raw)


def non_comparable_combinations(config: dict) -> set[tuple[str, str]]:
    combos = set()
    for item in config.get("comparability", {}).get("non_comparable_combinations", []):
        combos.add((item["site_key"], item["workflow_version"]))
    return combos
