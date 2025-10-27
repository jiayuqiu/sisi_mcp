import unittest
from mcp_conductor.detector.plot_ship_congestion import plot_ship_congestion


class TestMCPServer(unittest.TestCase):
    def setUp(self) -> None:
        # change run_date and pipe_name if your dummy CSVs use different values
        self.run_date = "2023-12-31"
        self.pipe_name = "曼德海峡"
        return super().setUp()

    def test_plot_congestion(self):
        path = plot_ship_congestion(self.run_date, self.pipe_name, month=3, day=0, output_dir="./tmp/images")
        print("Plot saved to:", path)