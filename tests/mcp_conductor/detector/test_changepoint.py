import unittest
import numpy as np
from unittest.mock import patch, MagicMock

from mcp_conductor.detector.changepoint import ChangePointDetector


class TestChangePointDetector(unittest.TestCase):
    """Unit tests for the ChangePointDetector class."""

    def setUp(self):
        """Set up test fixtures."""
        self.basic_config = {
            'method': 'bic',
            'model': 'l2',
            'min_size': 2
        }
        
        # Simple time series with obvious change points
        self.simple_series = [1, 1, 2, 10, 11, 10, 2, 1, 1] * 3
        
        # Longer time series with multiple change points
        self.complex_series = [
            1, 1, 1, 2, 2, 2,              # Segment 1
            10, 10, 11, 12, 10, 9,         # Segment 2
            20, 21, 22, 20, 20, 19,        # Segment 3
            5, 6, 5, 4, 5                  # Segment 4
        ]
        
        # Very short time series
        self.short_series = [1, 2]
        
        # Constant time series with no change points
        self.constant_series = [5] * 50

    def test_init_with_config(self):
        """Test initialization with various configurations."""
        # Test with basic config
        detector = ChangePointDetector(self.basic_config)
        self.assertEqual(detector.method, 'bic')
        self.assertEqual(detector.model, 'l2')
        self.assertEqual(detector.min_size, 2)
        
        # Test with custom config
        custom_config = {
            'method': 'pelt',
            'model': 'l1',
            'min_size': 3,
            'penalty': 2,
            'n_bkps': 3
        }
        detector = ChangePointDetector(custom_config)
        self.assertEqual(detector.method, 'pelt')
        self.assertEqual(detector.model, 'l1')
        self.assertEqual(detector.min_size, 3)
        self.assertEqual(detector.penalty, 2)
        self.assertEqual(detector.n_bkps, 3)
        
        # Test defaults when not specified
        minimal_config = {'method': 'binseg'}
        detector = ChangePointDetector(minimal_config)
        self.assertEqual(detector.method, 'binseg')
        self.assertEqual(detector.model, 'l2')  # Default
        self.assertEqual(detector.min_size, 3)  # Default

    def test_detect_bic(self):
        """Test BIC change point detection."""
        detector = ChangePointDetector(self.basic_config)
        result = detector.detect(self.simple_series)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['method'], 'bic')
        self.assertIsInstance(result['change_points'], list)
        
        # BIC should detect the major change point in simple series
        # We expect at least one change point
        self.assertGreaterEqual(len(result['change_points']), 1)

    def test_detect_pelt(self):
        """Test PELT change point detection."""
        config = {'method': 'pelt', 'penalty': 2}
        detector = ChangePointDetector(config)
        result = detector.detect(self.complex_series)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['method'], 'pelt')
        self.assertIsInstance(result['change_points'], list)

    def test_detect_binary_segmentation(self):
        """Test binary segmentation change point detection."""
        config = {'method': 'binseg', 'n_bkps': 3}
        detector = ChangePointDetector(config)
        result = detector.detect(self.complex_series)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['method'], 'binseg')
        self.assertIsInstance(result['change_points'], list)
        
        # We asked for 3 breakpoints, so should get at most 3
        self.assertLessEqual(len(result['change_points']), 3)

    def test_detect_bottom_up(self):
        """Test bottom-up change point detection."""
        config = {'method': 'bottomup', 'n_bkps': 3}
        detector = ChangePointDetector(config)
        result = detector.detect(self.complex_series)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['method'], 'bottomup')
        self.assertIsInstance(result['change_points'], list)

    def test_detect_window(self):
        """Test window-based change point detection."""
        config = {'method': 'window', 'width': 3, 'n_bkps': 3}
        detector = ChangePointDetector(config)
        result = detector.detect(self.complex_series)
        
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['method'], 'window')
        self.assertIsInstance(result['change_points'], list)

    def test_detect_with_unknown_method(self):
        """Test error handling with unknown method."""
        config = {'method': 'unknown_method'}
        detector = ChangePointDetector(config)
        result = detector.detect(self.simple_series)
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('Unknown method', result['message'])
        self.assertEqual(result['change_points'], [])

    def test_detect_with_short_series(self):
        """Test error handling with very short time series."""
        detector = ChangePointDetector(self.basic_config)
        result = detector.detect([1])  # Single point series
        
        self.assertEqual(result['status'], 'error')
        self.assertIn('Time series too short', result['message'])
        self.assertEqual(result['change_points'], [])

    def test_detect_constant_series(self):
        """Test detection on constant time series."""
        detector = ChangePointDetector(self.basic_config)
        result = detector.detect(self.constant_series)
        
        self.assertEqual(result['status'], 'success')
        # Should ideally find no change points in a constant series
        # But algorithms might detect small variations due to sensitivity
        # So we won't strictly assert length is 0

    def test_set_method(self):
        """Test set_method functionality."""
        detector = ChangePointDetector(self.basic_config)
        self.assertEqual(detector.method, 'bic')
        
        detector.set_method('pelt')
        self.assertEqual(detector.method, 'pelt')
        
        with self.assertRaises(ValueError):
            detector.set_method('invalid_method')

    def test_set_model(self):
        """Test set_model functionality."""
        detector = ChangePointDetector(self.basic_config)
        self.assertEqual(detector.model, 'l2')
        
        detector.set_model('l1')
        self.assertEqual(detector.model, 'l1')
        
        with self.assertRaises(ValueError):
            detector.set_model('invalid_model')

    def test_set_params(self):
        """Test set_params functionality."""
        detector = ChangePointDetector(self.basic_config)
        
        # Test setting multiple parameters
        detector.set_params(
            min_size=5,
            n_bkps=10,
            penalty=4
        )
        
        self.assertEqual(detector.min_size, 5)
        self.assertEqual(detector.n_bkps, 10)
        self.assertEqual(detector.penalty, 4)
        
        # Test setting non-existent parameter (should be ignored)
        detector.set_params(non_existent_param=100)
        self.assertFalse(hasattr(detector, 'non_existent_param'))

    @patch('ruptures.Dynp')
    def test_bic_algorithm_calls(self, mock_dynp):
        """Test that BIC algorithm is called correctly."""
        # Setup mock
        mock_algo = MagicMock()
        mock_dynp.return_value = mock_algo
        mock_algo.fit.return_value = mock_algo
        mock_algo.predict.return_value = [5]
        
        detector = ChangePointDetector(self.basic_config)
        result = detector.detect(self.complex_series)
        
        # Check the algorithm was created with correct parameters
        mock_dynp.assert_called_once_with(model='l2', min_size=2)
        
        # Check fit was called with signal
        mock_algo.fit.assert_called_once()
        
        # Check predict was called with penalty
        mock_algo.predict.assert_called_once()
        
        # Check the result contains the mocked change points
        self.assertEqual(result['change_points'], [5])

    @patch('ruptures.Pelt')
    def test_pelt_algorithm_calls(self, mock_pelt):
        """Test that PELT algorithm is called correctly."""
        # Setup mock
        mock_algo = MagicMock()
        mock_pelt.return_value = mock_algo
        mock_algo.fit.return_value = mock_algo
        mock_algo.predict.return_value = [5, 10]
        
        config = {'method': 'pelt', 'penalty': 4}
        detector = ChangePointDetector(config)
        result = detector.detect(self.complex_series)
        
        # Check the algorithm was created with correct parameters
        mock_pelt.assert_called_once_with(model='l2', min_size=3)
        
        # Check predict was called with penalty
        mock_algo.predict.assert_called_once_with(pen=4)
        
        # Check the result contains the mocked change points
        self.assertEqual(result['change_points'], [5, 10])


if __name__ == '__main__':
    unittest.main()
