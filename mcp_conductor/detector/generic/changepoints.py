import numpy as np
import ruptures as rpt
from typing import Dict, Any, List, Union

from mcp_conductor.detector.generic.base_detector import BaseDetector


class ChangePointDetector(BaseDetector):
    def __init__(self, config: Dict[str, Any]) -> None:
        """
        Initialize the change point detector with configuration.
        
        Args:
            config: Configuration dictionary with parameters:
                - method: Detection method ('bic', 'pelt', 'binseg', 'bottomup', 'window'), default method: pelt
                - model: Cost model ('l1', 'l2', 'rbf', etc.)
                - min_size: Minimum segment size (default: 3)
                - penalty: Penalty term for BIC/PELT (default: 'default')
                - n_bkps: Number of breakpoints for methods that require it (default: 3)
                - jump: Jump value for approximation methods (default: 5)
                - width: Window width for window-based method (default: 5)
        """
        super().__init__(config)
        self.method = self.config.get('method', 'pelt')
        self.model = self.config.get('model', 'l2')
        self.min_size = self.config.get('min_size', 3)
        self.penalty = self.config.get('penalty', 'default')
        self.n_bkps = self.config.get('n_bkps', 3)
        self.jump = self.config.get('jump', 5)
        self.width = self.config.get('width', 5)
        self.algo = None

    def detect(self, value: Union[List[float], np.ndarray]) -> Dict[str, Any]:
        """
        Detect change points in a time series.
        
        Args:
            input_data: Time series data as a list or numpy array
            
        Returns:
            Dict[str, Any]: Detection results including change point indices
        """

        # Convert input to numpy array if it's a list
        signal = np.array(value) if isinstance(value, list) else value
        
        # Check if we have enough data points
        if len(signal) < self.min_size:
            return {'change_points': [], 'status': 'error', 'message': 'Time series too short'}
            
        # Select and run the appropriate algorithm
        if self.method == 'bic':
            change_points = self._detect_bic(signal)
        elif self.method == 'pelt':
            change_points = self._detect_pelt(signal)
        elif self.method == 'binseg':
            change_points = self._detect_binary_segmentation(signal)
        elif self.method == 'bottomup':
            change_points = self._detect_bottom_up(signal)
        elif self.method == 'window':
            change_points = self._detect_window(signal)
        else:
            return {'change_points': [], 'status': 'error', 'message': f'Unknown method: {self.method}'}
        return {'change_points': change_points, 'status': 'success', 'method': self.method, 'message': ''}
            
    
    def _detect_bic(self, signal: np.ndarray) -> List[int]:
        """
        Detect change points using Bayesian Information Criterion (BIC).
        
        Args:
            signal: The time series signal to analyze
            
        Returns:
            List[int]: Indices of detected change points
        """
        # Create and fit algorithm
        algo = rpt.Dynp(model=self.model, min_size=self.min_size)
        algo.fit(signal)
        
        if isinstance(self.penalty, (int, float)) and self.penalty != 'default':
            # Higher penalty = fewer breakpoints, lower penalty = more breakpoints
            # We'll use a simple inverse relationship
            n_bkps = max(1, min(10, int(10/self.penalty)))
        else:
            n_bkps = self.n_bkps
            
        changes = algo.predict(n_bkps=n_bkps)
        
        # Remove last index as it's just the length of the signal
        if changes and changes[-1] == len(signal):
            changes = changes[:-1]
            
        return changes
    
    def _detect_pelt(self, signal: np.ndarray) -> List[int]:
        """
        Detect change points using PELT algorithm.
        
        Args:
            signal: The time series signal to analyze
            
        Returns:
            List[int]: Indices of detected change points
        """
        algo = rpt.Pelt(model=self.model, min_size=self.min_size)
        algo.fit(signal)
        
        # For PELT, we can specify penalty parameter
        if self.penalty == 'default':
            pen = 3  # Default penalty
        else:
            pen = self.penalty
            
        changes = algo.predict(pen=pen)
        
        # Remove last index
        if changes and changes[-1] == len(signal):
            changes = changes[:-1]
            
        return changes
    
    def _detect_binary_segmentation(self, signal: np.ndarray) -> List[int]:
        """
        Detect change points using Binary Segmentation.
        
        Args:
            signal: The time series signal to analyze
            
        Returns:
            List[int]: Indices of detected change points
        """
        algo = rpt.Binseg(model=self.model, min_size=self.min_size, jump=self.jump)
        algo.fit(signal)
        
        # Binary segmentation requires specifying number of breakpoints
        changes = algo.predict(n_bkps=self.n_bkps)
        
        # Remove last index
        if changes and changes[-1] == len(signal):
            changes = changes[:-1]
            
        return changes
    
    def _detect_bottom_up(self, signal: np.ndarray) -> List[int]:
        """
        Detect change points using Bottom-Up Segmentation.
        
        Args:
            signal: The time series signal to analyze
            
        Returns:
            List[int]: Indices of detected change points
        """
        algo = rpt.BottomUp(model=self.model, min_size=self.min_size, jump=self.jump)
        algo.fit(signal)
        
        # Bottom-Up requires specifying number of breakpoints
        changes = algo.predict(n_bkps=self.n_bkps)
        
        # Remove last index
        if changes and changes[-1] == len(signal):
            changes = changes[:-1]
            
        return changes
    
    def _detect_window(self, signal: np.ndarray) -> List[int]:
        """
        Detect change points using Window-based detection.
        
        Args:
            signal: The time series signal to analyze
            
        Returns:
            List[int]: Indices of detected change points
        """
        algo = rpt.Window(width=self.width, model=self.model, min_size=self.min_size)
        algo.fit(signal)
        
        # Window method requires specifying number of breakpoints
        changes = algo.predict(n_bkps=self.n_bkps)
        
        # Remove last index
        if changes and changes[-1] == len(signal):
            changes = changes[:-1]
            
        return changes

    def set_method(self, method: str) -> None:
        """
        Set the change point detection method.
        
        Args:
            method: One of 'bic', 'pelt', 'binseg', 'bottomup', 'window'
        """
        valid_methods = ['bic', 'pelt', 'binseg', 'bottomup', 'window']
        if method not in valid_methods:
            raise ValueError(f"Method must be one of {valid_methods}")
        self.method = method
    
    def set_model(self, model: str) -> None:
        """
        Set the cost model for change point detection.
        
        Args:
            model: One of 'l1', 'l2', 'rbf', etc.
        """
        valid_models = ['l1', 'l2', 'rbf', 'linear', 'normal', 'ar']
        if model not in valid_models:
            raise ValueError(f"Model must be one of {valid_models}")
        self.model = model
    
    def set_params(self, **params) -> None:
        """
        Set multiple parameters at once.
        
        Args:
            **params: Parameters to set (method, model, min_size, etc.)
        """
        for param, value in params.items():
            if hasattr(self, param):
                setattr(self, param, value)
