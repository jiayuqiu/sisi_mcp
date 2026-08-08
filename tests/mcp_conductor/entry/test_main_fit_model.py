from unittest.mock import call, patch

from mcp_conductor.entry import main_fit_model


def test_fit_model_orchestrates_every_location_type_and_metric():
    def fitted_rows(**kwargs):
        return [{"location_type": kwargs["location_type"], "metric": kwargs["metric"], "status": "OK"}]

    with patch.object(main_fit_model, "fit_roll_percentile_parameters", side_effect=fitted_rows) as fit:
        result = main_fit_model.fit_model(
            recent_records=90,
            as_of_date_id=20260701,
            fit_start=20250101,
            persist=False,
        )

    assert [(row["location_type"], row["metric"]) for row in result] == [
        ("pipe", "ship_cnt"),
        ("pipe", "duration"),
        ("port", "ship_cnt"),
        ("port", "duration"),
    ]
    assert fit.call_args_list == [
        call(
            location_type=location_type,
            metric=metric,
            recent_records=90,
            as_of_date_id=20260701,
            fit_start=20250101,
            persist=False,
        )
        for location_type in ("pipe", "port")
        for metric in ("ship_cnt", "duration")
    ]


def test_main_maps_dry_run_to_non_persistent_fit():
    expected = [{"location_type": "port", "metric": "duration", "status": "OK"}]
    with patch.object(main_fit_model, "fit_model", return_value=expected) as fit_model:
        result = main_fit_model.main(
            [
                "--dry_run",
                "--location_type", "port",
                "--metric", "duration",
                "--recent_records", "90",
                "--as_of", "20260701",
                "--fit_start", "20250101",
            ]
        )

    assert result == expected
    fit_model.assert_called_once_with(
        recent_records=90,
        as_of_date_id=20260701,
        fit_start=20250101,
        location_type="port",
        metric="duration",
        persist=False,
    )
