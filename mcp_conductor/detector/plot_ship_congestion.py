"""Plot ship-count and duration detector output for one pipe or port."""

from pathlib import Path
import re
import sqlite3

import matplotlib.pyplot as plt
import pandas as pd


DB_PATH = Path("./data/sisi.sqlite")

LOCATION_SPECS = {
    "pipe": ("ship_cnt_in_pipe", "pipe_name"),
    "port": ("ship_cnt_in_port", "port_name"),
}

DIRECTION_COLORS = {
    "LOW": "#7c3aed",
    "HIGH": "#ea580c",
    "MIXED": "#db2777",
    "NORMAL": "#059669",
    "UNKNOWN": "#d97706",
}


def _safe_filename(value: str) -> str:
    cleaned = re.sub(r"[^\w.-]+", "_", value, flags=re.UNICODE).strip("_")
    return cleaned or "location"


def plot_ship_congestion(
    run_date: str,
    pipe_name: str,
    month: int = 3,
    day: int = 0,
    output_dir: str | Path = "./tmp/images",
    *,
    dimension: str = "pipe",
    db_path: str | Path = DB_PATH,
) -> str:
    """Render count and duration series with directional anomaly markers.

    ``month`` and ``day`` define the lookback from ``run_date``. The result table is
    joined by location name and date so both channel directions and the combined
    regime can be shown without modifying the source observations.
    """
    if dimension not in LOCATION_SPECS:
        raise ValueError(f"dimension must be one of {sorted(LOCATION_SPECS)}, got {dimension!r}")
    if month < 0 or day < 0:
        raise ValueError("month and day must be non-negative")

    end_date = pd.Timestamp(run_date)
    start_date = end_date - pd.DateOffset(months=month) - pd.Timedelta(days=day)
    start_date_id = int(start_date.strftime("%Y%m%d"))
    end_date_id = int(end_date.strftime("%Y%m%d"))
    source_table, name_column = LOCATION_SPECS[dimension]

    query = f"""
        SELECT
            s.date_id,
            s.ship_cnt,
            s.duration,
            a.anomaly_flag,
            a.direction,
            a.duration_anomaly_flag,
            a.duration_direction,
            a.duration_status,
            a.regime
        FROM {source_table} s
        LEFT JOIN m_pipe_anomaly_roll_percentile a
          ON a.location_type = ?
         AND a.pipe_name = s.{name_column}
         AND a.date_id = s.date_id
        WHERE s.{name_column} = ?
          AND s.date_id BETWEEN ? AND ?
        ORDER BY s.date_id
    """
    with sqlite3.connect(str(db_path)) as conn:
        data = pd.read_sql_query(
            query,
            conn,
            params=(dimension, pipe_name, start_date_id, end_date_id),
        )

    if data.empty:
        raise ValueError(
            f"No {dimension} observations for {pipe_name!r} between "
            f"{start_date.date()} and {end_date.date()}"
        )

    data["date"] = pd.to_datetime(data["date_id"].astype(str), format="%Y%m%d")
    fig, (count_ax, duration_ax) = plt.subplots(
        2,
        1,
        figsize=(12, 7),
        sharex=True,
        constrained_layout=True,
    )

    count_ax.plot(data["date"], data["ship_cnt"], color="#0f766e", linewidth=1.5)
    count_ax.fill_between(data["date"], data["ship_cnt"], color="#5eead4", alpha=0.18)
    count_ax.set_ylabel("Ship count")
    count_ax.grid(axis="y", alpha=0.2)

    count_anomalies = data[data["anomaly_flag"] == 1]
    for direction, group in count_anomalies.groupby("direction", dropna=False):
        direction_name = str(direction) if pd.notna(direction) else "UNKNOWN"
        count_ax.scatter(
            group["date"],
            group["ship_cnt"],
            color=DIRECTION_COLORS.get(direction_name, DIRECTION_COLORS["UNKNOWN"]),
            s=34,
            label=f"Count {direction_name}",
            zorder=3,
        )

    duration_ax.plot(data["date"], data["duration"], color="#0284c7", linewidth=1.5)
    duration_ax.set_ylabel("Duration")
    duration_ax.set_xlabel("Date")
    duration_ax.grid(axis="y", alpha=0.2)

    duration_anomalies = data[data["duration_anomaly_flag"] == 1]
    for direction, group in duration_anomalies.groupby("duration_direction", dropna=False):
        direction_name = str(direction) if pd.notna(direction) else "UNKNOWN"
        duration_ax.scatter(
            group["date"],
            group["duration"],
            color=DIRECTION_COLORS.get(direction_name, DIRECTION_COLORS["UNKNOWN"]),
            marker="D",
            s=34,
            label=f"Duration {direction_name}",
            zorder=3,
        )

    reportable = data[
        data["regime"].notna()
        & ~data["regime"].isin(["NORMAL", "COUNT_NORMAL", "DURATION_NORMAL"])
    ].tail(8)
    for row in reportable.itertuples():
        target_ax = duration_ax if pd.notna(row.duration) else count_ax
        target_y = row.duration if pd.notna(row.duration) else row.ship_cnt
        target_ax.annotate(
            row.regime,
            (row.date, target_y),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=7,
            color="#334155",
        )

    count_ax.set_title(f"{pipe_name}: count/duration anomaly regimes through {run_date}")
    if not count_anomalies.empty:
        count_ax.legend(loc="upper left", fontsize=8)
    if not duration_anomalies.empty:
        duration_ax.legend(loc="upper left", fontsize=8)

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    image_path = output_path / f"ship_congestion_{_safe_filename(pipe_name)}_{end_date_id}.png"
    fig.savefig(image_path, dpi=160)
    plt.close(fig)
    return str(image_path)
