from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseDetector(ABC):
    """
    Abstract base class for all detectors in the system.
    
    All detector implementations should inherit from this class and
    implement the required abstract methods.
    """
    
    def __init__(self, config: Dict[str, Any] | None = None):
        """
        Initialize the detector with optional configuration.
        
        Args:
            config: Dictionary containing configuration parameters for the detector
        """
        self.config = config or {}
    
    @abstractmethod
    def detect(self, input_data: Any) -> Dict[str, Any]:
        """
        Perform detection on the input data.
        
        Args:
            input_data: The input data to perform detection on
            
        Returns:
            Dict[str, Any]: Detection results
        """
        raise NotImplementedError(
            "BaseDetector hasn't supported `detect`."
        )
    
    def validate_config(self) -> bool:
        """
        Validate the configuration of the detector.
        TODO: will add pydantic contrain class for validation
        
        Returns:
            bool: True if configuration is valid, False otherwise
        """
        # Default implementation assumes config is valid
        raise NotImplementedError(
            "BaseDetector hasn't supported `validate_config`."
        )
    
    def set_method(self):
        """TODO: add in future"""
        raise NotImplementedError(
            "BaseDetector hasn't supported `set_method`."
        )

    def set_model(self):
        """TODO: add in future"""
        raise NotImplementedError(
            "BaseDetector hasn't supported `set_model`."
        )

    def set_params(self):
        """TODO: add in future"""
        raise NotImplementedError(
            "BaseDetector hasn't supported `set_params`."
        )