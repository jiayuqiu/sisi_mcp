import pandas as pd
from datetime import datetime, timedelta
import glob
import os

from mcp_conductor.detector.generic.changepoints import ChangePointDetector


def pipe_detect_engine(run_date: str, month: int = 3, day: int = 0) -> dict[str, pd.DataFrame]:
    """
    TODO: currently, this function is just for demonstration purposes. will optimize later.
    """
    config = {
        'method': 'pelt', 
        'penalty': 2,
        'width': 7  # time window, 7 days
    }
    detector = ChangePointDetector(config)

    # load data from dummy folder
    dummy_data_folder = "/home/jerry/codebase/sisimcp/data/dummy"
    dummy_data_files = glob.glob(os.path.join(dummy_data_folder, "*.csv"))
    df_list = []
    for _fn in dummy_data_files:
        _df = pd.read_csv(_fn)
        df_list.append(_df)

    df = pd.concat(df_list, ignore_index=True)

    # base on run_date find out the records in monitor time window
    # group by strait name
    pipe_gdf = df.groupby("通道名称")
    all_changepoints_result = {}
    for pipe_name, group in pipe_gdf:
        run_date_obj = datetime.strptime(str(run_date), "%Y-%m-%d")
        start_date_obj = run_date_obj - timedelta(days=day) - pd.DateOffset(months=month)
        start_date_id = int(start_date_obj.strftime("%Y%m%d"))
        run_date_id = int(run_date_obj.strftime("%Y%m%d"))
        
        group = group.loc[
            (group['日期'] >= start_date_id) & (group['日期'] <= run_date_id)
        ]
        if group.shape[0] == 0:
            # there is no data in the time window, skip this pipe
            continue

        # feed the ship cnt into detector, will get changepoints as expected.
        result = detector.detect(group["【集装箱】港口在通道船舶数量(Ship)"].tolist())
        changepoints_df = group.iloc[result["change_points"]]
        all_changepoints_result[pipe_name] = changepoints_df
    return all_changepoints_result
