from unittest.mock import patch

from mcp_conductor.entry import main_monitor_roll_percentile as entry


def test_monitor_cli_maps_arguments(capsys):
    rows = [
        {
            "direction": "ANY",
            "location_type": "pipe",
            "location_name": "Pipe A",
            "metric": "ship_cnt",
            "eligible_count": 30,
            "flagged_count": 2,
            "flag_rate": 2 / 30,
            "status": "OK",
        }
    ]
    with patch.object(entry, "monitor_roll_percentile", return_value=rows) as monitor:
        result = entry.main(
            [
                "--end_date", "2026-07-26",
                "--window_days", "14",
                "--min_samples", "10",
                "--alert_rate", "0.2",
                "--dry_run",
            ]
        )

    assert result == rows
    monitor.assert_called_once_with(
        end_date_id="2026-07-26",
        window_days=14,
        min_eligible_samples=10,
        alert_flag_rate=0.2,
        persist=False,
    )
    assert "Pipe A" in capsys.readouterr().out
