"""Deterministic research data generator (seed 20250710).

Produces the four research tables for the retrospective stage-attribution
study:

  events.csv        shared event log (same shape as the STAR-TAT log)
  quality_events.csv  rule-labeled delay/rework labels (ground truth for eval)
  sample_classes.csv  same-class baseline grouping definitions
  load_staffing.csv   load and staffing/equipment configuration snapshots
  stage_map.csv     byte copy of the frozen event dictionary v1.0

Planted structure (all rates are generator parameters, not model parameters):
  - roughly 12% of released cases carry a rule-labeled DELAY label
  - roughly 8% carry a rule-labeled REWORK label (a repeated stage event)
  - roughly 3% are two-stage simultaneous deviations (attribution is not
    unique; the engine must report AMBIGUOUS_STAGES)
  - a share of cases come from a site-version combination registered as not
    comparable (NOT_COMPARABLE_SITE)
  - one sample class is deliberately small (< 30 cases) so the baseline
    sufficiency rule (INSUFFICIENT_BASELINE) is exercised by the real run
  - about 1% of cases carry one unmapped raw event code (registered in the
    non-comparable ledger and excluded from stage computation)

The generator is deterministic for a given seed: the same seed, the same
parameters and the same dictionary reproduce the tables byte for byte.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pandas as pd

from ..common.hashing import sha256_file
from .dictionary import CANONICAL_STAGES, PACKAGED_DICTIONARY

# reverse index: (site_key, workflow_version) -> {canonical_stage: event_code_raw}
_dict_df = pd.read_csv(PACKAGED_DICTIONARY, dtype=str)
CODE_INDEX: dict[tuple[str, str], dict[str, str]] = {}
for _row in _dict_df.to_dict("records"):
    _key = (_row["site_key"], _row["workflow_version"])
    CODE_INDEX.setdefault(_key, {})[_row["canonical_stage"]] = _row["event_code_raw"]

SEED_DEFAULT = 20250710
N_TOTAL = 3500
RATE_DELAY = 0.145
RATE_REWORK = 0.08
RATE_UNMAPPED = 0.01
SHARE_STRONG = 0.30
SHARE_AMBIGUOUS = 0.22
SHARE_DECOY = 0.48
TARGET_DELAY_ADJUDICATED = 420  # ~12% of 3500, incl. manual case reviews

SITE_WEIGHTS = {"SITE_A": 0.40, "SITE_B": 0.35, "SITE_C": 0.25}
VERSION_WEIGHTS = {"WF_V1": 0.30, "WF_V2": 0.35, "WF_V3": 0.35}

VERSION_WINDOWS = {
    # (earliest received, latest received) per workflow-version validity
    # window from the frozen dictionary; WF_V3's end carries an era margin
    # so every downstream timestamp stays at or before 2026-06-30.
    "WF_V1": (pd.Timestamp("2024-01-15", tz="UTC"), pd.Timestamp("2024-09-01", tz="UTC")),
    "WF_V2": (pd.Timestamp("2024-09-01", tz="UTC"), pd.Timestamp("2025-06-01", tz="UTC")),
    "WF_V3": (pd.Timestamp("2025-06-01", tz="UTC"), pd.Timestamp("2026-06-08", tz="UTC")),
}

# class_id -> (test_family, priority_class, source_category, valid_from,
# valid_to, weight, median_total_hours, min_received_at)
CLASSES = {
    "CLS-01": ("PANEL", "ROUTINE", "ONC", "2024-01-01", "2026-06-30", 0.24, 240.0, None),
    "CLS-02": ("PANEL", "STAT", "ONC", "2024-01-01", "2026-06-30", 0.14, 168.0, None),
    "CLS-03": ("WES", "ROUTINE", "GERM", "2024-01-01", "2026-06-30", 0.20, 288.0, None),
    "CLS-04": ("WES", "STAT", "GERM", "2024-01-01", "2026-06-30", 0.10, 192.0, None),
    "CLS-05": ("WGS", "ROUTINE", "PEDS", "2025-03-01", "2026-06-30", 0.08, 384.0, "2025-03-05"),
    "CLS-06": ("CARRIER", "ROUTINE", "GERM", "2024-01-01", "2026-06-30", 0.12, 192.0, None),
    "CLS-07": ("PANEL", "ROUTINE", "PEDS", "2024-01-01", "2026-06-30", 0.11, 216.0, None),
    "CLS-08": ("WES", "STAT", "PEDS", "2024-01-01", "2026-06-30", 0.0, 192.0, None),
}
CLS_SMALL = "CLS-08"
CLS_SMALL_N = 22

# stage share of total duration and natural lognormal sigma
STAGE_SHARES = {
    "SAMPLE_RECEIVED": 0.04,
    "ACCESSIONED": 0.06,
    "LIBRARY_PREPARED": 0.22,
    "SEQUENCING_STARTED": 0.30,
    "ANALYSIS_COMPLETE": 0.24,
    "REVIEWED": 0.08,
    "RELEASED": 0.06,
}
SIGMA_LN_NATURAL = 0.10
SIGMA_LN_PLANTED = 0.03

# plant mechanics
STRONG_FACTOR = (4.5, 5.5)
AMBIGUOUS_FACTOR = (3.8, 4.6)
DECOY_FACTOR = (1.35, 1.45)
STRONG_STAGE_POOL = ["LIBRARY_PREPARED", "SEQUENCING_STARTED", "ANALYSIS_COMPLETE"]
HIGH_QUEUE_STAGE_POOL = ["LIBRARY_PREPARED", "SEQUENCING_STARTED"]
QUEUE_DELAY_WEIGHTS = {1: 0.06, 2: 0.09, 3: 0.14, 4: 0.19}

ADJUDICATORS = ["QA_01", "QA_02", "QA_03", "QA_04"]
RULE_VERSION = "RR-2025-07-28A"
MAX_ADJUDICATED_AT = pd.Timestamp("2026-06-29", tz="UTC")

SITE_SOURCE_SYSTEM = {
    "SITE_A": "LIS-SITE_A",
    "SITE_B": "LIS-SITE_B",
    "SITE_C": "LIS-SITE_C",
}
SEQUENCING_SOURCE_SYSTEM = {
    "SITE_A": "WB-SITE_A",
    "SITE_B": "WB-SITE_B",
    "SITE_C": "WB-SITE_C",
}
SITE_QUEUE_BASE = {"SITE_A": 480.0, "SITE_B": 520.0, "SITE_C": 300.0}
# Raw feed codes absent from the frozen dictionary; one per unmasked case
# (registered as unmapped and excluded, same convention as the shared log).
UNMAPPED_CODES = ("XADM", "XERR", "XMISC", "XQCC")

# Data window close: every timestamp in every table is bounded by this
# instant (all date concepts in this repository end at 2026-06-30).
HORIZON_END = pd.Timestamp("2026-06-30T00:00:00Z")


def _fmt(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%dT%H:%M:%SZ")


def generate_tables(seed: int = SEED_DEFAULT, n_total: int = N_TOTAL) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)

    # ---------- case table ----------
    sites = list(SITE_WEIGHTS)
    versions = list(VERSION_WEIGHTS)
    n = int(n_total)
    site_arr = rng.choice(sites, n, p=list(SITE_WEIGHTS.values()))
    version_arr = rng.choice(versions, n, p=list(VERSION_WEIGHTS.values()))

    # classes: CLS-08 fixed small; the rest by weight
    other_ids = [c for c in CLASSES if c != CLS_SMALL]
    other_weights = np.array([CLASSES[c][5] for c in other_ids], dtype=float)
    other_weights = other_weights / other_weights.sum()
    n_other = n - CLS_SMALL_N
    class_arr = np.empty(n, dtype=object)
    idx = rng.permutation(n)
    class_arr[idx[:CLS_SMALL_N]] = CLS_SMALL
    class_arr[idx[CLS_SMALL_N:]] = rng.choice(other_ids, n_other, p=other_weights)

    case_keys = [f"CASE_{i:08d}" for i in range(1, n + 1)]

    received = np.empty(n, dtype="datetime64[s]")
    version_order = list(VERSION_WEIGHTS)
    for i in range(n):
        lo, hi = VERSION_WINDOWS[version_arr[i]]
        min_ts = CLASSES[class_arr[i]][7]
        if min_ts:
            min_lo = pd.Timestamp(min_ts, tz="UTC")
            # the class is only valid from min_ts; move to a later workflow
            # version window when the drawn window ends before that date
            while lo > min_lo or hi < min_lo:
                v_idx = version_order.index(version_arr[i])
                version_arr[i] = version_order[min(v_idx + 1, len(version_order) - 1)]
                lo, hi = VERSION_WINDOWS[version_arr[i]]
                if version_arr[i] == version_order[-1]:
                    break
            lo = max(lo, min_lo)
        span = int((hi - lo).total_seconds())
        received[i] = np.datetime64(
            (lo + pd.Timedelta(seconds=int(rng.integers(0, span + 1)))).strftime("%Y-%m-%dT%H:%M:%S")
        )

    cases = pd.DataFrame(
        {
            "case_key": case_keys,
            "site_key": site_arr,
            "workflow_version": version_arr,
            "sample_class": class_arr,
            "received_at_utc": received,
        }
    )

    # ---------- load staffing snapshots ----------
    staffing_rows = []
    for site in sites:
        for version in versions:
            lo, hi = VERSION_WINDOWS[version]
            cursor = pd.Timestamp(lo.strftime("%Y-%m-01"), tz="UTC")
            while cursor <= hi:
                month = cursor.month
                base = SITE_QUEUE_BASE[site]
                seasonal = 1.0 + 0.12 * np.sin(2 * np.pi * (month + (0 if site != "SITE_C" else 3)) / 12.0)
                vfactor = 1.10 if version == "WF_V3" else 1.0
                queue = base * seasonal * vfactor * float(rng.lognormal(0.0, 0.05))
                staffing = "FULL"
                if (site == "SITE_A" and version == "WF_V2" and month in (7, 8)) or (
                    site == "SITE_B" and version == "WF_V2" and month in (1, 2, 3)
                ) or (site == "SITE_C" and version == "WF_V3" and month == 11):
                    staffing = "REDUCED"
                if site == "SITE_B" and version == "WF_V2" and month == 2:
                    staffing = "CRITICAL"
                equipment = "FALLBACK" if staffing in ("REDUCED", "CRITICAL") and rng.random() < 0.7 else "PRIMARY"
                staffing_rows.append(
                    {
                        "site_key": site,
                        "workflow_version": version,
                        "snapshot_at_utc": cursor + pd.Timedelta(hours=9),
                        "queue_size": int(round(queue)),
                        "staffing_category": staffing,
                        "equipment_class": equipment,
                    }
                )
                cursor = pd.Timestamp((cursor + pd.DateOffset(months=1)).strftime("%Y-%m-01"), tz="UTC")
    load_staffing = pd.DataFrame(staffing_rows)

    # queue quantile per (site, version) snapshot
    qq = (
        load_staffing.groupby(["site_key", "workflow_version"])["queue_size"]
        .transform(lambda s: pd.qcut(s.rank(method="first"), 4, labels=[1, 2, 3, 4]))
    ).astype(int)
    snap_index = (
        load_staffing[["site_key", "workflow_version", "snapshot_at_utc"]]
        .assign(queue_quartile=qq.to_numpy())
        .set_index(["site_key", "workflow_version", "snapshot_at_utc"])["queue_quartile"]
        .sort_index()
    )
    case_quartile = []
    for i in range(n):
        key = (site_arr[i], version_arr[i])
        sub = snap_index.loc[key]
        past = sub[sub.index <= pd.Timestamp(received[i], tz="UTC")]
        case_quartile.append(int(past.iloc[-1] if len(past) else 1))
    cases["queue_quartile"] = case_quartile

    # ---------- plant assignment ----------
    n_delay = int(round(n * RATE_DELAY))
    n_rework = int(round(n * RATE_REWORK))
    # allocate delays per queue quartile with weights, then correct the total
    pop_q = {q: int((cases["queue_quartile"] == q).sum()) for q in (1, 2, 3, 4)}
    scale = n_delay / sum(pop_q[q] * QUEUE_DELAY_WEIGHTS[q] for q in (1, 2, 3, 4))
    counts = {q: int(round(pop_q[q] * QUEUE_DELAY_WEIGHTS[q] * scale)) for q in (1, 2, 3, 4)}
    counts = {q: min(counts[q], pop_q[q]) for q in (1, 2, 3, 4)}
    while sum(counts.values()) != n_delay:
        diff = n_delay - sum(counts.values())
        for q in (4, 3, 2, 1):
            if diff == 0:
                break
            if diff > 0 and counts[q] < pop_q[q]:
                add = min(diff, pop_q[q] - counts[q])
                counts[q] += add
                diff -= add
            elif diff < 0 and counts[q] > 0:
                sub = min(-diff, counts[q])
                counts[q] -= sub
                diff += sub
    delay_idx = []
    for q in (1, 2, 3, 4):
        pool = np.where((cases["queue_quartile"] == q).to_numpy())[0]
        chosen = rng.choice(pool, size=counts[q], replace=False)
        delay_idx.extend(chosen.tolist())
    delay_idx = np.array(sorted(delay_idx))

    delay_set = set(delay_idx.tolist())
    rework_pool = np.array([i for i in range(n) if i not in delay_set])
    rework_idx = np.array(sorted(rng.choice(rework_pool, size=n_rework, replace=False).tolist()))
    rework_set = set(rework_idx.tolist())

    n_strong = int(round(n_delay * SHARE_STRONG))
    n_ambiguous = int(round(n_delay * SHARE_AMBIGUOUS))
    n_decoy = n_delay - n_strong - n_ambiguous
    perm = rng.permutation(delay_idx)
    strong_idx = set(perm[:n_strong].tolist())
    ambiguous_idx = set(perm[n_strong : n_strong + n_ambiguous].tolist())
    decoy_idx = set(perm[n_strong + n_ambiguous :].tolist())

    plant_type = np.full(n, "NONE", dtype=object)
    plant_stages = [None] * n
    for i in strong_idx:
        plant_type[i] = "STRONG"
    for i in ambiguous_idx:
        plant_type[i] = "AMBIGUOUS"
    for i in decoy_idx:
        plant_type[i] = "DECOY"
    for i in rework_set:
        plant_type[i] = "REWORK"

    # ---------- stage durations and events ----------
    event_rows = []
    delay_candidates = []
    rework_rows = []
    unmasked = set(rng.choice(n, size=int(round(n * RATE_UNMAPPED)), replace=False).tolist())
    case_meta = []
    for i in range(n):
        cls = class_arr[i]
        site = site_arr[i]
        version = version_arr[i]
        median_total = CLASSES[cls][6]
        # The local event stream of SITE_C lacks the sequencing step (frozen
        # dictionary mapping); the offsite sequencing time folds into the
        # library-to-analysis gap, mirroring the shared dictionary's declared
        # comparability note.
        stages = [s for s in CANONICAL_STAGES if not (site == "SITE_C" and s == "SEQUENCING_STARTED")]
        shares = dict(STAGE_SHARES)
        if site == "SITE_C":
            shares["ANALYSIS_COMPLETE"] += shares.pop("SEQUENCING_STARTED")
        strong_pool = [s for s in STRONG_STAGE_POOL if s in stages]
        high_queue_pool = [s for s in HIGH_QUEUE_STAGE_POOL if s in stages]
        durations = {}
        pt = plant_type[i]
        if pt == "STRONG":
            s = _pick_strong_stage(rng, cases["queue_quartile"][i], strong_pool, high_queue_pool)
            factor = float(rng.uniform(*STRONG_FACTOR))
            plant_stages[i] = [s]
            factor_map = {s: factor}
        elif pt == "AMBIGUOUS":
            s1, s2 = _pick_two(rng, strong_pool)
            factor_map = {s1: float(rng.uniform(*AMBIGUOUS_FACTOR)), s2: float(rng.uniform(*AMBIGUOUS_FACTOR))}
            plant_stages[i] = [s1, s2]
        elif pt == "DECOY":
            band = list(rng.choice(stages, size=min(6, len(stages)), replace=False))
            s_b = band[int(rng.integers(0, len(band)))]
            factor_map = {s: float(rng.uniform(*DECOY_FACTOR)) for s in band}
            plant_stages[i] = [s_b] + [s for s in band if s != s_b]
        elif pt == "REWORK":
            s = stages[int(rng.integers(0, len(stages)))]
            factor_map = {}
            plant_stages[i] = [s]
        else:
            factor_map = {}
        for s in stages:
            dur = median_total * shares[s]
            sigma = SIGMA_LN_PLANTED if s in factor_map else SIGMA_LN_NATURAL
            dur *= factor_map.get(s, 1.0) * float(np.exp(rng.normal(0.0, sigma)))
            durations[s] = dur

        received_ts = pd.Timestamp(received[i], tz="UTC")
        t = received_ts
        rows = []
        occ = {}
        repeat_stage = plant_stages[i][0] if pt == "REWORK" else None
        for s in stages:
            dur = durations[s]
            t = t + pd.Timedelta(hours=float(dur))
            rows.append((s, t))
            if s == repeat_stage:
                repeat_at = t - pd.Timedelta(hours=0.3 * float(dur))
                rows.append((s, repeat_at))
        # unmapped extra event
        if i in unmasked:
            span = (t - received_ts).total_seconds()
            extra_at = received_ts + pd.Timedelta(seconds=float(rng.uniform(0.2, 0.8) * span))
            rows.append(("__UNMAPPED__", extra_at))
        rows.sort(key=lambda r: r[1])
        released_ts = min(t, HORIZON_END)

        code_index = CODE_INDEX[(site, version)]
        for s, ts in rows:
            if s == "__UNMAPPED__":
                code = str(rng.choice(UNMAPPED_CODES))
            else:
                code = code_index[s]
            version_no = occ.get(code, 0) + 1
            occ[code] = version_no
            known = ts + pd.Timedelta(minutes=float(rng.lognormal(np.log(120), 1.1)))
            # The data window closes at HORIZON_END; no timestamp may pass it.
            if ts > HORIZON_END:
                ts = HORIZON_END
            if known > HORIZON_END:
                known = HORIZON_END
            source = SEQUENCING_SOURCE_SYSTEM[site] if s == "SEQUENCING_STARTED" else SITE_SOURCE_SYSTEM[site]
            event_rows.append(
                {
                    "case_key": case_keys[i],
                    "event_code_raw": code,
                    "occurred_at_utc": _fmt(ts),
                    "known_at_utc": _fmt(known),
                    "source_system": source,
                    "record_version": version_no,
                }
            )

        # delay plants: candidate labels resolved after the p90 pass
        if pt in ("STRONG", "AMBIGUOUS", "DECOY"):
            if pt == "STRONG":
                s = plant_stages[i][0]
                ratio = factor_map[s]
                basis = f"stage {s}; duration {ratio:.1f}x class median"
            elif pt == "AMBIGUOUS":
                basis = "stages " + ",".join(sorted(plant_stages[i])) + "; joint deviation"
            else:
                basis = f"stage {plant_stages[i][0]}; manual case review of queue log; timestamps diffuse"
            delay_candidates.append(
                {
                    "case_key": case_keys[i],
                    "released_at": released_ts,
                    "basis": basis,
                    "index": i,
                }
            )
        elif pt == "REWORK":
            s = plant_stages[i][0]
            rework_rows.append(
                {
                    "case_key": case_keys[i],
                    "released_at": released_ts,
                    "basis": f"stage {s}; repeated events (2)",
                    "index": i,
                }
            )
        case_meta.append(
            {
                "case_key": case_keys[i],
                "site_key": site,
                "workflow_version": version,
                "sample_class": cls,
                "received_at_utc": _fmt(received_ts),
                "released_at_utc": _fmt(released_ts),
                "plant_type": pt,
                "plant_stages": ",".join(plant_stages[i]) if plant_stages[i] else "",
                "queue_quartile": int(cases["queue_quartile"][i]),
            }
        )

    # ---- second pass: label delay candidates strictly by the predefined
    # rule (total duration above the class p90, computed identically to the
    # engine) plus a manual case-review sample of borderline candidates, so
    # that the rule-labeled delay share reaches the target rate. The review-path
    # sample represents reviews the rules alone would have missed.
    case_table = pd.DataFrame(case_meta).sort_values("case_key").reset_index(drop=True)
    case_table["total_hours"] = (
        (pd.to_datetime(case_table["released_at_utc"], format="ISO8601")
         - pd.to_datetime(case_table["received_at_utc"], format="ISO8601"))
        .dt.total_seconds() / 3600.0
    )
    p90 = case_table.groupby("sample_class")["total_hours"].quantile(0.90)
    p90_of = case_table.set_index("case_key")["sample_class"].map(p90)
    quality_rows = []
    for row in rework_rows:
        quality_rows.append(
            {
                "case_key": row["case_key"],
                "event_type": "REWORK",
                "released_at": row["released_at"],
                "basis": row["basis"],
                "index": row["index"],
            }
        )
    flagged_delay = []
    unflagged_decoy = []
    for row in delay_candidates:
        if case_table.loc[case_table["case_key"] == row["case_key"], "total_hours"].iloc[0] > p90_of[row["case_key"]]:
            flagged_delay.append(row)
        elif "manual case review" in row["basis"]:
            unflagged_decoy.append(row)
    manual_n = max(0, TARGET_DELAY_ADJUDICATED - len(flagged_delay))
    manual_n = min(manual_n, len(unflagged_decoy))
    if manual_n:
        chosen = rng.choice(np.arange(len(unflagged_decoy)), size=manual_n, replace=False)
        flagged_delay.extend(unflagged_decoy[i] for i in sorted(chosen.tolist()))
    for row in flagged_delay:
        quality_rows.append(
            {
                "case_key": row["case_key"],
                "event_type": "DELAY",
                "released_at": row["released_at"],
                "basis": row["basis"],
                "index": row["index"],
            }
        )
    quality_rows.sort(key=lambda r: (r["case_key"], r["event_type"]))
    qa_counter = 0
    for row in quality_rows:
        qa_counter += 1
        adjudicated_at = row["released_at"] + pd.Timedelta(days=int(rng.integers(1, 26)))
        if adjudicated_at > MAX_ADJUDICATED_AT:
            adjudicated_at = MAX_ADJUDICATED_AT
        row["event_id"] = f"QE-{qa_counter:06d}"
        row["rule_version"] = RULE_VERSION
        row["adjudicated_at"] = _fmt(adjudicated_at)
        row["adjudicated_by"] = ADJUDICATORS[row["index"] % len(ADJUDICATORS)]
        del row["released_at"]
        del row["index"]
    quality_events = pd.DataFrame(quality_rows).reset_index(drop=True)

    events = pd.DataFrame(event_rows).sort_values(["case_key", "occurred_at_utc"]).reset_index(drop=True)

    sample_classes = pd.DataFrame(
        [
            {
                "class_id": c,
                "test_family": CLASSES[c][0],
                "priority_class": CLASSES[c][1],
                "source_category": CLASSES[c][2],
                "valid_from": CLASSES[c][3],
                "valid_to": CLASSES[c][4],
            }
            for c in CLASSES
        ]
    )

    return {
        "events": events,
        "quality_events": quality_events,
        "sample_classes": sample_classes,
        "load_staffing": load_staffing.drop(columns=["queue_quartile"], errors="ignore"),
        "case_table": case_table,
    }


def _pick_strong_stage(
    rng: np.random.Generator,
    queue_quartile: int,
    strong_pool: list[str],
    high_queue_pool: list[str],
) -> str:
    if queue_quartile >= 3 and rng.random() < 0.65 and high_queue_pool:
        pool = high_queue_pool
    else:
        pool = strong_pool
    return pool[int(rng.integers(0, len(pool)))]


def _pick_two(rng: np.random.Generator, strong_pool: list[str]) -> tuple[str, str]:
    pool = list(strong_pool)
    rng.shuffle(pool)
    return pool[0], pool[1]


def write_tables(tables: dict[str, pd.DataFrame], output_dir: str | Path) -> dict[str, str]:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    # shared case registry (same shape as the STAR-TAT case table)
    case_table = tables["case_table"].copy()
    case_table["test_family"] = case_table["sample_class"].map(lambda c: CLASSES[c][0])
    case_table["priority_class"] = case_table["sample_class"].map(lambda c: CLASSES[c][1])
    case_table["source_category"] = case_table["sample_class"].map(lambda c: CLASSES[c][2])
    case_table["is_released"] = 1
    cases_df = case_table[
        [
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
    ]

    load_staffing = tables["load_staffing"].copy()
    load_staffing["snapshot_at_utc"] = load_staffing["snapshot_at_utc"].map(_fmt)

    name_map = {
        "events": "events.csv",
        "quality_events": "quality_events.csv",
        "sample_classes": "sample_classes.csv",
    }
    hashes = {}
    cases_df.to_csv(out / "cases.csv", index=False)
    hashes["cases.csv"] = sha256_file(out / "cases.csv")
    for key, filename in name_map.items():
        path = out / filename
        tables[key].to_csv(path, index=False)
        hashes[filename] = sha256_file(path)
    load_staffing.to_csv(out / "load_staffing.csv", index=False)
    hashes["load_staffing.csv"] = sha256_file(out / "load_staffing.csv")
    stage_map_out = out / "stage_map.csv"
    shutil.copyfile(PACKAGED_DICTIONARY, stage_map_out)
    hashes["stage_map.csv"] = sha256_file(stage_map_out)
    return hashes


def write_params(output_dir: str | Path, seed: int, tables: dict[str, pd.DataFrame]) -> None:
    case_table = tables["case_table"]
    n_total = len(case_table)
    params = {
        "seed": seed,
        "n_cases_total": n_total,
        "n_delay_labeled": int((tables["quality_events"]["event_type"] == "DELAY").sum()),
        "n_rework_labeled": int((tables["quality_events"]["event_type"] == "REWORK").sum()),
        "n_two_stage_deviation": int(
            (case_table["plant_type"] == "AMBIGUOUS").sum()
        ),
        "n_not_comparable_combo": int(
            ((case_table["site_key"] == "SITE_C") & (case_table["workflow_version"] == "WF_V1")).sum()
        ),
        "n_small_class_cases": int((case_table["sample_class"] == CLS_SMALL).sum()),
        "n_unmapped_event_cases": int(tables["events"]["event_code_raw"].isin(UNMAPPED_CODES).sum()),
        "rule_version": RULE_VERSION,
        "label_rules": "configs/label_rules.yaml",
        "dictionary": "src/retro_trace/a1/data/stage_map_v1_0.csv",
    }
    with open(Path(output_dir) / "params.json", "w", encoding="utf-8") as fh:
        json.dump(params, fh, indent=2, sort_keys=True)
        fh.write("\n")
