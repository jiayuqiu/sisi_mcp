import pandas as pd
import logging
from datetime import datetime, timedelta
from typing import Any
from sqlalchemy import text

from mcp_conductor.detector.roll_percentile import RollingPercentileDetector
from mcp_conductor.resources.utils.db import get_engine
from mcp_conductor.resources.utils.sisi_dataclasses import ROLLING_PERCENTILE_FLAG as FLAG

logger = logging.getLogger(__name__)


PIPE_TABLE = "ship_cnt_in_pipe"
PORT_TABLE = "ship_cnt_in_port"
PARAM_TABLE = "m_roll_percentile_parameter"


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
                pipe_name,
                date_id,
                ship_cnt,
                duration
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


def get_port_ship_cnt(port_name: str, start_date_id: int, end_date_id: int, engine) -> pd.DataFrame:
    get_port_cnt_sql = f"""
        SELECT
            *
        FROM
            ship_cnt_in_port
        WHERE
            port_name = '{port_name}'
            and date_id >= {start_date_id} and date_id <= {end_date_id}
    """
    df = pd.read_sql(
        get_port_cnt_sql, con=engine
    )

    if df.shape[0] == 0:
        logger.warning(f"From {start_date_id} to {end_date_id}, {port_name} there is no port ship cnt data.")

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


def get_port_name_list(engine) -> list[str]:
    """
    Return all distinct strait names present in ship_cnt_in_port.

    Args:
        engine: SQLAlchemy engine.

    Returns:
        List of port_name strings.

    Raises:
        ValueError: if the table contains no rows.
    """
    sql = """
        SELECT DISTINCT
            port_name
        FROM
            ship_cnt_in_port
        WHERE
            port_name NOT LIKE 'test_%';
    """
    df = pd.read_sql(sql, con=engine)
    # logger.info("SQL: %s", sql)
    if df.shape[0] == 0:
        raise ValueError(f"There is no port ship cnt data from {engine}.")

    return df.port_name.tolist()


def get_roll_percentile_parameters(
    location_type: str, location_name: str, metric: str, run_date_id: int, engine
) -> dict | None:
    """Return the single parameter row in force for a location on ``run_date_id``."""
    sql = text(
        f"""
        SELECT lower_bound, upper_bound, anomaly_threshold, interval_days, status
        FROM {PARAM_TABLE}
        WHERE location_type = :location_type
          AND location_name = :location_name
          AND metric = :metric
          AND valid_from_date_id <= :run_date_id
          AND (valid_to_date_id IS NULL OR valid_to_date_id >= :run_date_id)
        ORDER BY valid_from_date_id DESC
        LIMIT 1
        """
    )
    with engine.connect() as connection:
        row = connection.execute(
            sql,
            {
                "location_type": location_type,
                "location_name": location_name,
                "metric": metric,
                "run_date_id": run_date_id,
            },
        ).mappings().first()
    return dict(row) if row else None


def detect_one_location(
    signals: pd.DataFrame,
    location_col_name: str,
    name_str: str,
    run_date_id: int,
    detector: RollingPercentileDetector,
    parameters: dict | None,
) -> dict:
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
                "anomaly_flag"  : int,    # FLAG value (0-4)
                "quantile_10"   : float,  # 10th-percentile ship count
                "quantile_25"   : float,  # 25th-percentile ship count
                "quantile_75"   : float,  # 75th-percentile ship count
                "quantile_90"   : float,  # 90th-percentile ship count
                "anomaly_ratio" : float,  # outlier days / interval_days
            }
    """
    if signals.empty:
        logger.warning("No data for pipe_name=%s, skipping.", name_str)
        anomaly_detection = {
            "anomaly_flag": FLAG.NO_DATA,
            "quantile_10": None,
            "quantile_25": None,
            "quantile_75": None,
            "quantile_90": None,
            "anomaly_ratio": None,
        }
    else:
        anomaly_detection = detector.detect(
            value=signals,
            location_col_name=location_col_name,
            name_str=name_str,
            run_date_id=run_date_id,
            parameters=parameters,
        )
    detection_result = {
        location_col_name: name_str,
        "run_date_id": run_date_id,
        "anomaly_flag": anomaly_detection["anomaly_flag"],
        "quantile_10": anomaly_detection.get("quantile_10"),
        "quantile_25": anomaly_detection.get("quantile_25"),
        "quantile_75": anomaly_detection.get("quantile_75"),
        "quantile_90": anomaly_detection.get("quantile_90"),
        "anomaly_ratio": anomaly_detection.get("anomaly_ratio"),
    }
    return detection_result


def run_detect(app_type: str,
               app_detect_config: dict,
               run_date_id: int,
               start_date_id: int,
               detector: RollingPercentileDetector,
               engine) -> list:
    # run detect
    detection_result_list = []
    for _name in app_detect_config["name_list"]:
        if app_type == "pipe":
            load_signals = get_pipe_ship_cnt
        elif app_type == "port":
            load_signals = get_port_ship_cnt
        else:
            raise ValueError(f"Unsupported app_type: {app_type}")

        parameters = get_roll_percentile_parameters(
            location_type=app_type,
            location_name=_name,
            metric="ship_cnt",
            run_date_id=run_date_id,
            engine=engine,
        )
        signals = load_signals(_name, start_date_id, run_date_id, engine)
        detection_result = detect_one_location(
            signals,
            app_type,
            _name,
            run_date_id,
            detector,
            parameters,
        )
        detection_result_list.append(detection_result)
    return detection_result_list


def rp_detect_engine(run_date: str) -> dict:
    """
    Run rolling percentile anomaly detection across all straits for a given date.

    For each strait in ship_cnt_in_pipe:
        1. Load its full historical ship count data.
        2. Run RollingPercentileDetector to check whether recent traffic is anomalous.
        3. Collect the result.

    Args:
        run_date: detection date in YYYY-MM-DD format.

    Returns:
        List of dicts, one per strait:
            {
                "pipe_name"     : str,
                "run_date_id"   : int,    # YYYYMMDD
                "anomaly_flag"  : int,    # FLAG value (0-4)
                "quantile_10"   : float,  # 10th-percentile ship count
                "quantile_25"   : float,  # 25th-percentile ship count
                "quantile_75"   : float,  # 75th-percentile ship count
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
    # group by pipe/port name
    detect_config = {
        "pipe": {
            "name_list": get_pipe_name_list(engine),
            "table": PIPE_TABLE
        },
        "port": {
            "name_list": get_port_name_list(engine),
            "table": PORT_TABLE
        }
    }

    app_detect_results = {}
    for app_type, app_detect_config in detect_config.items():
        detection_result = run_detect(
            app_type=app_type,
            app_detect_config=app_detect_config,
            run_date_id=run_date_id,
            start_date_id=start_date_id,
            detector=detector,
            engine=engine
        )
        app_detect_results[app_type] = detection_result
    return app_detect_results
