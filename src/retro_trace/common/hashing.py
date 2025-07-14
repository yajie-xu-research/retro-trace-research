"""Deterministic hashing helpers.

The result hash for a run is built from a fixed field subset (config hash,
data hash, seed, rule version, and result file hashes) so that the same seed,
input, and configuration always reproduce the same hash byte for byte.
Wall-clock fields (utc, operator, command) are deliberately outside the
hash scope.
"""

from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: str | Path) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def dictionary_pin(dictionary_path: str | Path, canonical_stages: tuple[str, ...]) -> str:
    """Pin hash of the frozen event dictionary.

    Covers the exact dictionary CSV bytes plus the canonical stage list, so a
    change to either the mapping table or the stage enumeration invalidates
    the pin.
    """
    file_hash = sha256_file(dictionary_path)
    payload = file_hash + "\n" + ",".join(canonical_stages) + "\n"
    return sha256_text(payload)


def data_hash(data_dir: str | Path, files: list[str]) -> str:
    """Hash of the input table files that feed the pipeline."""
    parts = []
    for name in sorted(files):
        parts.append(name)
        parts.append(sha256_file(Path(data_dir) / name))
    return sha256_text("\n".join(parts))


def result_hash(
    config_hash: str,
    data_hash_value: str,
    seed: int,
    rule_version: str,
    result_file_hashes: dict[str, str],
) -> str:
    parts = [config_hash, data_hash_value, str(seed), rule_version]
    for name in sorted(result_file_hashes):
        parts.append(name)
        parts.append(result_file_hashes[name])
    return sha256_text("\n".join(parts))
