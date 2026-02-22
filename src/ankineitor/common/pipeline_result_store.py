from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd


PIPELINE_RESULTS_ROOT = Path("output/pipeline_results_by_profile")


def sanitize_profile_id_for_path(profile_id: str) -> str:
    """Return a filesystem-safe directory name for a profile id."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", str(profile_id or "").strip().lower())
    return cleaned or "unknown_profile"


def get_profile_output_dir(profile_id: str) -> Path:
    """Return output directory path for a profile."""
    return PIPELINE_RESULTS_ROOT / sanitize_profile_id_for_path(profile_id)


def save_pipeline_results_csv(
    df_results: pd.DataFrame,
    profile_id: str,
    *,
    now: Optional[datetime] = None,
) -> Path:
    """
    Persist pipeline results as CSV under a profile-specific folder.

    Files are written with a timestamped filename to keep each run separate.
    """
    timestamp = (now or datetime.now()).strftime("%Y%m%d_%H%M%S_%f")
    output_dir = get_profile_output_dir(profile_id)
    output_dir.mkdir(parents=True, exist_ok=True)
    file_path = output_dir / f"pipeline_results_{timestamp}.csv"
    df_results.to_csv(file_path, index=False, encoding="utf-8-sig")
    return file_path


def list_saved_profiles() -> List[str]:
    """List profile folder names that have saved pipeline CSVs."""
    if not PIPELINE_RESULTS_ROOT.exists():
        return []
    return sorted(
        [path.name for path in PIPELINE_RESULTS_ROOT.iterdir() if path.is_dir()]
    )


def list_saved_csv_files_for_profile(profile_id: str) -> List[Path]:
    """List saved CSV files for a profile, newest first."""
    profile_dir = get_profile_output_dir(profile_id)
    if not profile_dir.exists():
        return []
    csv_files = [path for path in profile_dir.glob("*.csv") if path.is_file()]
    return sorted(csv_files, key=lambda path: path.stat().st_mtime, reverse=True)
