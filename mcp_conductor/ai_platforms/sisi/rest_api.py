"""
SISI LLM model client
After we captured the weather and news summary text (EN), feed the text into SISI LLM model to rephase and 
translate the text into chinese.
"""

import requests
from typing import Dict, Any

from mcp_conductor.ai_platforms.base_rest_api import BaseAIClient
from mcp_conductor.ai_platforms.tools import get_token_from_env


class SISIClient(BaseAIClient):
    def __init__(self, api_key: str | None = None) -> None:
        """This client is to interact with SISI LLM client

        Args:
            api_key (str | None, optional): api token. Defaults to None.
        """
        super().__init__(api_key)
        self.base_url = "http://101.231.77.77:9997"
        self.api_key = api_key or get_token_from_env("SISI_API_KEY")
        if not self.api_key:
            raise ValueError("API key must be provided or set in SISI_API_KEY environment variable")

        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def search_and_ask(
            self, 
            question: str, 
            model: str = "Qwen3-14B-pre-train-awq-4bit", 
            web_search: bool = False, 
            temperature: float = 0.7, 
            max_tokens: int | None = None, 
            stream: bool = False
    ) -> Dict[str, Any]:
        """Request to rephase text

        Args:
            question (str): Your context
            model (str, optional): model name. Defaults to "Qwen3-14B-pre-train-awq-4bit".
            web_search (bool, optional): If need web search. Defaults to False.
            temperature (float, optional): controls how creative or deterministic the model’s output is. Defaults to 0.7.
            max_tokens (int | None, optional): max token size. Defaults to None.
            stream (bool, optional): if stream chat. Defaults to False.

        Returns:
            Dict[str, Any]: result
        """
        url = f"{self.base_url}/v1/chat/completions"

        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": question
                }
            ],
            "max_tokens": 1024,
            "temperature": temperature,
            "stream": stream
        }

        try:
            response = requests.post(url, headers=self.headers, json=payload, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
