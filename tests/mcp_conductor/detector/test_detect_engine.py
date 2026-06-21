import unittest
import pandas as pd

from mcp_conductor.detector.generic.rolling_percentile import RollingPercentileDetector
from mcp_conductor.detector.detect_engine import (
    PIPE_TABLE,
    PORT_TABLE,
    run_detect, 
    get_pipe_name_list, 
    get_port_name_list,
    get_engine,
    rp_detect_engine
)


class TestDetectEngine(unittest.TestCase):
    def setUp(self):
        self.engine = get_engine()
        self.detector = RollingPercentileDetector()
    
    def test_get_engine(self):
        get_engine()

    def test_run_detect_pipe(self):
        """_summary_
        """
        pipe_detect_config = {
            "name_list": get_pipe_name_list(self.engine),
            "table": PIPE_TABLE
        }
        detect_result = run_detect(
            app_type="pipe",
            app_detect_config=pipe_detect_config,
            run_date_id=20260501,
            start_date_id=20250401,
            detector=self.detector,
            engine=self.engine
        )

    def test_run_detect_port(self):
        """_summary_
        """
        port_detect_config = {
            "name_list": get_port_name_list(self.engine),
            "table": PORT_TABLE
        }
        detect_result = run_detect(
            app_type="port",
            app_detect_config=port_detect_config,
            run_date_id=20260501,
            start_date_id=20250401,
            detector=self.detector,
            engine=self.engine
        )
        print(detect_result)
    
    def test_rp_detect_engine(self):
        app_detect_results = rp_detect_engine(run_date="2026-04-01")
        print(app_detect_results)
