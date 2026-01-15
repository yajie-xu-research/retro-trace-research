"""Ground-truth copy-on-write for run directories.

The rule-labeled quality-event labels (quality_events.csv) are copied
verbatim
into the isolated data/_ground_truth/ directory of a run so that evaluation
can read them afterwards. This module contains the ONLY write path to that
directory. No feature, attribution, or baseline code may import this module or
touch the directory; the isolation is enforced by tests that delete the
directory and verify byte-identical attribution outputs.
"""

from __future__ import annotations

import shutil
from pathlib import Path

from ..common.run_layout import ground_truth_path


def stage_ground_truth(data_dir: str | Path, run_dir: str | Path) -> str:
    """Copy the quality-event labels into the run's isolated ground-truth dir."""
    src = Path(data_dir) / "quality_events.csv"
    dst = ground_truth_path(run_dir)
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    return str(dst)
