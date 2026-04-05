import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Any

from dify.api.core.mcp.server.streamable_http import convert_input_form_to_parameters
from mcp_conductor.detector.generic.rolling_percentile import RollingPercentileDetector
from mcp_conductor.resources.utils.db import get_engine
from mcp_conductor.resources.utils.sisi_dataclasses import ROLLING_PERCENTILE_FLAG as FLAG

logger = logging.getLogger(__name__)


def get_pipe_ship_cnt(pipe_name: str, start_date_id: int, end_date_id: int, engine) -> pd.DataFrame:
    """
    Query all ship count records for a single strait from ship_cnt_in_pipe.

    Args:
        pipe_name    : strait name to filter on.
        start_date_id: window start in YYYYMMDD (used only for the warning message).
        end_date_id  : window end in YYYYMMDD (used only for the warning message).
        engine       : SQLAlchemy engine.

    Returns:
        DataFrame with all columns from ship_cnt_in_pipe for the given strait.
    """
    get_ship_cnt_sql = f"""
            SELECT 
                * 
            FROM 
                ship_cnt_in_pipe 
            WHERE 
                pipe_name = '{pipe_name}'
                and date_id >= {start_date_id} and date_id <= {end_date_id}
        """
    df = pd.read_sql(
        get_ship_cnt_sql, con=engine
    )

    if df.shape[0] == 0:
        logger.warning(f"From {start_date_id} to {end_date_id}, {pipe_name} there is no pipe ship cnt data.")

    return df


def get_pipe_name_list(engine) -> list[str]:
    """
    Return all distinct strait names present in ship_cnt_in_pipe.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        List of pipe_name strings.

    Raises:
        ValueError: if the table contains no rows.
    """
    sql = f"""
        SELECT DISTINCT 
            pipe_name 
        FROM 
            ship_cnt_in_pipe
        WHERE
            pipe_name NOT LIKE 'test_%';
    """
    df = pd.read_sql(sql, con=engine)
    # logger.info("SQL: %s", sql)
    if df.shape[0] == 0:
        raise ValueError(f"There is no pipe ship cnt data from {engine}.")

    return df.pipe_name.tolist()


def single_pipe_detect(signals: pd.DataFrame,
                       pipe_name: str,
                       run_date_id: int,
                       detector: RollingPercentileDetector) -> dict:
    """
    Run rolling-percentile detection on a single strait's historical data.

    If the DataFrame is empty, returns FLAG.NO_DATA with None for all
    numeric fields. Otherwise delegates to the detector.

    Args:
        signals     : historical ship count DataFrame (columns: date_id, ship_cnt).
        pipe_name   : strait name, passed through to the detector and result.
        run_date_id : reference date in YYYYMMDD format.
        detector    : configured RollingPercentileDetector instance.

    Returns:
        dict:
            {
                "pipe_name"     : str,
                "run_date_id"   : int,    # YYYYMMDD
                "anomaly_flag"  : int,    # FLAG value (0–4)
                "quantile_10"   : float,  # 10th-percentile ship count
                "quantile_90"   : float,  # 90th-percentile ship count
                "anomaly_ratio" : float,  # outlier days / interval_days
            }
    """
    if signals.empty:
        logger.warning("No data for pipe_name=%s, skipping.", pipe_name)
        anomaly_detection = {
            "anomaly_flag": FLAG.NO_DATA,
            "quantile_10": None,
            "quantile_90": None,
            "anomaly_ratio": None,
        }
    else:
        # feed the ship cnt into detector, will get changepoints as expected.
        anomaly_detection = detector.detect(value=signals, pipe_name=pipe_name, run_date_id=run_date_id)
    detection_result = {
        "pipe_name": pipe_name,
        "run_date_id": run_date_id,
        "anomaly_flag": anomaly_detection["anomaly_flag"],
        "quantile_10": anomaly_detection.get("quantile_10"),
        "quantile_90": anomaly_detection.get("quantile_90"),
        "anomaly_ratio": anomaly_detection.get("anomaly_ratio"),
    }
    return detection_result


def pipe_rp_detect_engine(run_date: str, pipe_name: str | None) -> list[dict[str, Any]]:
    """
    Run rolling percentile anomaly detection across all straits for a given date.

    For each strait in ship_cnt_in_pipe:
        1. Load its full historical ship count data.
        2. Run RollingPercentileDetector to check whether recent traffic is anomalous.
        3. Collect the result.

    Args:
        run_date: detection date in YYYY-MM-DD format.
        pipe_name: Optional, if not None, output single pipe_name detection result.

    Returns:
        List of dicts, one per strait:
            {
                "pipe_name"     : str,
                "run_date_id"   : int,    # YYYYMMDD
                "anomaly_flag"  : int,    # FLAG value (0–4)
                "quantile_10"   : float,  # 10th-percentile ship count
                "quantile_90"   : float,  # 90th-percentile ship count
                "anomaly_ratio" : float,  # outlier days / interval_days
            }
    """
    engine = get_engine()

    # set detector
    detector = RollingPercentileDetector()

    # set start and end date
    run_date_obj = datetime.strptime(str(run_date), "%Y-%m-%d")
    run_date_id = int(run_date_obj.strftime("%Y%m%d"))
    start_date_obj = run_date_obj - timedelta(days=detector.window)
    start_date_id = int(start_date_obj.strftime("%Y%m%d"))

    # base on run_date find out the records in monitor time window
    # group by pipe name
    pipe_name_list = get_pipe_name_list(engine)
    detection_result_list = []
    for _pipe_name in pipe_name_list:
        if (pipe_name is not None) and (_pipe_name != pipe_name):
            # only output one pipe detection result
            continue

        _signals = get_pipe_ship_cnt(_pipe_name, start_date_id, run_date_id, engine)
        detection_result = single_pipe_detect(
            _signals, _pipe_name, run_date_id, detector
        )
        detection_result_list.append(detection_result)
    return detection_result_list
