import pandas as pd
import logging
from datetime import datetime, timedelta
import glob
import os
from pathlib import Path
from sqlalchemy import create_engine

from mcp_conductor.detector.generic.changepoints import ChangePointDetector

logger = logging.getLogger(__name__)


def pipe_detect_engine(run_date: str, pipe_name: str, month: int = 1, day: int = 0) -> dict[str, pd.DataFrame]:
    """
    TODO: currently, this function is just for demonstration purposes. will optimize later.
    """
    config = {
        'method': 'sisi', 
        'penalty': 2,
        'width': 7  # time window, 7 days
    }
    detector = ChangePointDetector(config)

    # load data from sqlite
    db_path = Path("./data/sisi.sqlite")
    engine = create_engine(f"sqlite:///{db_path.absolute()}") # ensure this # ensure this is the correct path for the sqlite file. 
    get_ship_cnt_sql = f"SELECT * FROM ship_cnt_in_pipe WHERE pipe_name = '{pipe_name}'"
    df = pd.read_sql(  # TODO: optimize the where condition
        get_ship_cnt_sql, con=engine
    )
    logger.info("SQL: %s", get_ship_cnt_sql)

    if df.shape[0] == 0:
        raise ValueError(
            f"For {run_date}, {pipe_name} there is no pipe ship cnt data."
        )

    # base on run_date find out the records in monitor time window
    # group by strait name
    pipe_gdf = df.groupby("pipe_name")
    all_changepoints_result = {}
    for pipe_name, group in pipe_gdf:
        run_date_obj = datetime.strptime(str(run_date), "%Y-%m-%d")
        start_date_obj = run_date_obj - timedelta(days=day) - pd.DateOffset(months=month)
        start_date_id = int(start_date_obj.strftime("%Y%m%d"))
        run_date_id = int(run_date_obj.strftime("%Y%m%d"))
        
        group = group.loc[
            (group['date_id'] >= start_date_id) & (group['date_id'] <= run_date_id)
        ]
        if group.shape[0] == 0:
            # there is no data in the time window, skip this pipe
            continue

        # feed the ship cnt into detector, will get changepoints as expected.
        result = detector.detect(group["ship_cnt"].tolist(), pipe_name=pipe_name)
        changepoints_df = group.iloc[result["change_points"]]
        all_changepoints_result[pipe_name] = changepoints_df
    return all_changepoints_result
