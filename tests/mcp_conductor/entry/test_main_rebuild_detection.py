from unittest.mock import call, patch

import pytest

from mcp_conductor.entry import main_rebuild_detection


def test_rebuild_fits_previous_day_then_detects_current_day():
    with (
        patch.object(main_rebuild_detection, "backup_database") as backup,
        patch.object(main_rebuild_detection, "fit_model", return_value=[{"status": "OK"}]) as fit,
        patch.object(main_rebuild_detection, "traffic_detect") as detect,
    ):
        result = main_rebuild_detection.rebuild_detection(
            "2026-07-01",
            "2026-07-02",
        )

    backup.assert_called_once_with()
    assert fit.call_args_list == [
        call(as_of_date_id=20260630, persist=True),
        call(as_of_date_id=20260701, persist=True),
    ]
    assert detect.call_args_list == [call("2026-07-01"), call("2026-07-02")]
    assert result == [
        {"run_date": "2026-07-01", "as_of_date_id": 20260630, "fit_rows": 1, "detected": True},
        {"run_date": "2026-07-02", "as_of_date_id": 20260701, "fit_rows": 1, "detected": True},
    ]


def test_dry_run_previews_fits_without_backup_or_detection():
    with (
        patch.object(main_rebuild_detection, "backup_database") as backup,
        patch.object(main_rebuild_detection, "fit_model", return_value=[]) as fit,
        patch.object(main_rebuild_detection, "traffic_detect") as detect,
    ):
        result = main_rebuild_detection.rebuild_detection(
            "2026-08-01",
            "2026-08-01",
            dry_run=True,
        )

    backup.assert_not_called()
    fit.assert_called_once_with(as_of_date_id=20260731, persist=False)
    detect.assert_not_called()
    assert result[0]["detected"] is False


def test_rebuild_rejects_reversed_date_range():
    with pytest.raises(ValueError, match="start_date must be on or before end_date"):
        main_rebuild_detection.rebuild_detection("2026-08-02", "2026-08-01")


def test_main_maps_cli_options():
    with patch.object(main_rebuild_detection, "rebuild_detection", return_value=[]) as rebuild:
        main_rebuild_detection.main(
            [
                "--start-date", "2026-05-01",
                "--end-date", "2026-08-01",
                "--dry-run",
                "--no-backup",
            ]
        )

    rebuild.assert_called_once_with(
        "2026-05-01",
        "2026-08-01",
        dry_run=True,
        create_backup=False,
    )
