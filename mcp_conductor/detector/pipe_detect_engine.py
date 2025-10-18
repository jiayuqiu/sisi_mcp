import pandas as pd
from datetime import datetime, timedelta

from mcp_conductor.detector.generic.changepoints import ChangePointDetector


def pipe_detect_engine(run_date: str, month: int = 2, day: int = 0) -> pd.DataFrame:
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
    df = pd.read_csv("/home/jerry/codebase/sisimcp/data/dummy/malacca_strait_dummy.csv")

    # base on run_date find out the records in monitor time window
    run_date_obj = datetime.strptime(str(run_date), "%Y-%m-%d")
    start_date_obj = run_date_obj - timedelta(days=day) - pd.DateOffset(months=month)
    start_date_id = int(start_date_obj.strftime("%Y%m%d"))
    run_date_id = int(run_date_obj.strftime("%Y%m%d"))
    
    df = df.loc[
        (df['日期'] >= start_date_id) & (df['日期'] <= run_date_id)
    ]

    # feed the ship cnt into detector, will get changepoints as expected.
    result = detector.detect(df["【集装箱】港口在通道船舶数量(Ship)"].tolist())
    changepoints_df = df.iloc[result["change_points"]]
    return changepoints_df
