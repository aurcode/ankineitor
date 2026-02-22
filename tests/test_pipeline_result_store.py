from datetime import datetime
import os

import pandas as pd

from ankineitor.common import pipeline_result_store as result_store


def test_save_pipeline_results_csv_uses_profile_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(
        result_store, "PIPELINE_RESULTS_ROOT", tmp_path / "pipeline_results"
    )
    df = pd.DataFrame([{"word": "你好", "profile_id": "lotm_zh_en_es"}])

    output_path = result_store.save_pipeline_results_csv(
        df_results=df,
        profile_id="lotm_zh_en_es",
        now=datetime(2026, 2, 22, 10, 30, 0, 123456),
    )

    assert output_path.exists()
    assert output_path.parent.name == "lotm_zh_en_es"
    assert output_path.name.startswith("pipeline_results_20260222_103000_123456")


def test_list_saved_profiles_and_files_sorted_by_newest(tmp_path, monkeypatch):
    monkeypatch.setattr(
        result_store, "PIPELINE_RESULTS_ROOT", tmp_path / "pipeline_results"
    )
    df = pd.DataFrame([{"word": "test"}])

    old_file = result_store.save_pipeline_results_csv(
        df_results=df,
        profile_id="sp_russian",
        now=datetime(2026, 2, 22, 9, 0, 0, 0),
    )
    new_file = result_store.save_pipeline_results_csv(
        df_results=df,
        profile_id="sp_russian",
        now=datetime(2026, 2, 22, 10, 0, 0, 0),
    )

    os.utime(old_file, (1000, 1000))
    os.utime(new_file, (2000, 2000))

    profiles = result_store.list_saved_profiles()
    assert profiles == ["sp_russian"]

    files = result_store.list_saved_csv_files_for_profile("sp_russian")
    assert [path.name for path in files] == [new_file.name, old_file.name]


def test_sanitize_profile_id_for_path_handles_empty_and_special_chars():
    assert result_store.sanitize_profile_id_for_path("") == "unknown_profile"
    assert result_store.sanitize_profile_id_for_path("  SP Russian  ") == "sp_russian"
    assert (
        result_store.sanitize_profile_id_for_path("profile.with*symbols")
        == "profile_with_symbols"
    )
