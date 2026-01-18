"""
Base client for ai platform api request
"""

from abc import ABC
from typing import List, Dict, Any


class BaseAIClient(ABC):
    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize the base client.
        
        Args:
            api_key: API key. If not provided, will look for particular platform token from env variable.
        """
        self.timeout = 120  # unit: seconds

    def search_and_ask(
        self,
        question: str,
        model: str = "deepseek-chat",
        web_search: bool = True,
        temperature: float = 1.0,
        max_tokens: int | None = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            "This Client doesn't support web search and ask fucntion."
        )
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "deepseek-chat",
        web_search: bool = False,
        temperature: float = 1.0,
        max_tokens: int | None = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        raise NotImplementedError(
            "This Client doesn't support chat fucntion."
        )
    