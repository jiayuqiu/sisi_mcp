import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime, timedelta
import glob
import os
import re
import numpy as np
from pathlib import Path
from sqlalchemy import create_engine

from mcp_conductor.detector.generic.changepoints import ChangePointDetector


def _safe_filename(s: str) -> str:
    """Make a filesystem-safe filename from input string."""
    s = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_.-]", "_", s)
    return s


def plot_ship_congestion(run_date: str, pipe_name: str, month: int = 1, day: int = 0, output_dir: str = "./tmp/images") -> str:
    """
    Reads pipe data, detects changepoints, and generates a line chart of ship counts,
    highlighting congestion periods.

    Args:
        run_date: The end date for the analysis window (YYYY-MM-DD).
        pipe_name: The name of the channel to analyze.
        month: The number of months of data to include before the run_date.
        day: The number of days of data to include before the run_date.

    Returns:
        The file path of the generated plot image.
    """
    config = {
        'method': 'sisi',
        'penalty': 2,
        'width': 7  # time window, 7 days
    }
    detector = ChangePointDetector(config)

    # # Load data from dummy folder
    # dummy_data_folder = "/home/jerry/codebase/sisimcp/data/dummy"
    # dummy_data_files = glob.glob(os.path.join(dummy_data_folder, "*.csv"))
    # df_list = []
    # for _fn in dummy_data_files:
    #     _df = pd.read_csv(_fn)
    #     df_list.append(_df)

    # df = pd.concat(df_list, ignore_index=True)
    # df = pd.concat(df_list, ignore_index=True)
    # load data from sqlite
    db_path = Path("data/sisi.sqlite")
    engine = create_engine(f"sqlite:///{db_path.absolute()}") # ensure this # ensure this is the correct path for the sqlite file. 
    df = pd.read_sql(
        "SELECT * FROM ship_cnt_in_pipe", con=engine
    )

    # Filter data for the specified pipe and time window
    pipe_df = df[df["pipe_name"] == pipe_name].copy()
    
    run_date_obj = datetime.strptime(str(run_date), "%Y-%m-%d")
    start_date_obj = run_date_obj - timedelta(days=day) - pd.DateOffset(months=month)
    start_date_id = int(start_date_obj.strftime("%Y%m%d"))
    run_date_id = int(run_date_obj.strftime("%Y%m%d"))

    pipe_df = pipe_df.loc[
        (pipe_df['date_id'] >= start_date_id) & (pipe_df['date_id'] <= run_date_id)
    ]

    if pipe_df.empty:
        raise ValueError(f"No data found for pipe '{pipe_name}' in the given time window.")

    pipe_df['date_str'] = pd.to_datetime(pipe_df['date_id'].astype(str), format='%Y%m%d')
    pipe_df = pipe_df.sort_values('date_str')
    
    ship_counts = pipe_df["ship_cnt"].tolist()
    
    # Detect changepoints
    result = detector.detect(ship_counts, pipe_name)
    changepoints = result["change_points"]

    # Create plot
    # Set the font family to a Chinese font
    plt.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei'] # Replace with your chosen font name
    # Ensure the minus sign is displayed correctly
    plt.rcParams['axes.unicode_minus'] = False
    plt.figure(figsize=(15, 7))
    plt.plot(pipe_df['date_str'], ship_counts, label='Ship Count', color='blue', zorder=2)

    # Highlight congestion periods
    if changepoints:
        for i in range(len(changepoints) - 1):
            start_idx = changepoints[i]
            end_idx = changepoints[i+1]
            avg_count_period = np.mean(ship_counts[start_idx:end_idx])
            avg_count_total = np.mean(ship_counts)
            if avg_count_period > avg_count_total * 1.1: # Simple logic for congestion
                 plt.axvspan(pipe_df['date_str'].iloc[start_idx], pipe_df['date_str'].iloc[end_idx-1], color='red', alpha=0.3, label='Congestion' if i == 0 else "")

    plt.title(f'Ship Congestion Analysis for {pipe_name}')
    plt.xlabel('Date')
    plt.ylabel('Number of Ships')
    plt.grid(True, which='both', linestyle='--', linewidth=0.5)
    plt.legend()
    plt.tight_layout()

    # Save plot to a file (default ./tmp/images)
    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    safe_name = _safe_filename(pipe_name)
    output_path = os.path.join(output_dir, f"congestion_plot_{safe_name}_{timestamp}.png")
    plt.savefig(output_path)
    plt.close()

    return output_path
