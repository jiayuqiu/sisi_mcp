#!/usr/bin/env python3
"""
DeepSeek Web Search API Client
This script provides a simple interface to interact with DeepSeek's API with web search capabilities.
"""

import requests
import json
from typing import Optional, Dict, List, Any

from mcp_conductor.resources.sisi.APIs.base_rest_api import BaseAIClient
from mcp_conductor.resources.tools import get_token_from_env


class DeepSeekClient(BaseAIClient):
    """Client for interacting with DeepSeek API with web search support."""
    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize the DeepSeek client.
        
        Args:
            api_key: DeepSeek API key. If not provided, will look for DEEPSEEK_API_KEY env variable.
            base_url: Base URL for the DeepSeek API.
        """

        super().__init__(api_key)
        self.base_url = "https://api.deepseek.com"
        self.api_key = api_key or get_token_from_env("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("API key must be provided or set in DEEPSEEK_API_KEY environment variable")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def search_and_ask(
        self,
        question: str,
        model: str = "deepseek-chat",
        web_search: bool = True,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Ask a question using DeepSeek API with optional web search.
        
        Args:
            question: The question or prompt to ask.
            model: Model to use (default: "deepseek-chat").
            web_search: Whether to enable web search (default: True).
            temperature: Sampling temperature (0-2, default: 1.0).
            max_tokens: Maximum tokens in response (optional).
            stream: Whether to stream the response (default: False).
        
        Returns:
            Dict containing the API response.
        """
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": question
                }
            ],
            "temperature": temperature,
            "stream": stream
        }
        
        # Add web search parameter if enabled
        if web_search:
            payload["web_search"] = True
        
        # Add max_tokens if specified
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        try:
            if stream:
                return self._stream_request(url, payload)
            else:
                response = requests.post(url, headers=self.headers, json=payload, timeout=self.timeout)
                response.raise_for_status()
                return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
    
    def _stream_request(self, url: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle streaming responses."""
        try:
            with requests.post(url, headers=self.headers, json=payload, stream=True, timeout=self.timeout) as response:
                response.raise_for_status()
                full_content = ""
                
                for line in response.iter_lines():
                    if line:
                        line_str = line.decode('utf-8')
                        if line_str.startswith('data: '):
                            data_str = line_str[6:]
                            if data_str.strip() == '[DONE]':
                                break
                            try:
                                data = json.loads(data_str)
                                if 'choices' in data and len(data['choices']) > 0:
                                    delta = data['choices'][0].get('delta', {})
                                    content = delta.get('content', '')
                                    if content:
                                        print(content, end='', flush=True)
                                        full_content += content
                            except json.JSONDecodeError:
                                continue
                
                print()  # New line after streaming
                return {
                    "choices": [{
                        "message": {
                            "role": "assistant",
                            "content": full_content
                        }
                    }],
                    "streamed": True
                }
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}
    
    def chat(
        self,
        messages: List[Dict[str, str]],
        model: str = "deepseek-chat",
        web_search: bool = False,
        temperature: float = 1.0,
        max_tokens: Optional[int] = None,
        stream: bool = False
    ) -> Dict[str, Any]:
        """
        Have a multi-turn conversation with DeepSeek.
        
        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            model: Model to use (default: "deepseek-chat").
            web_search: Whether to enable web search (default: False).
            temperature: Sampling temperature (0-2, default: 1.0).
            max_tokens: Maximum tokens in response (optional).
            stream: Whether to stream the response (default: False).
        
        Returns:
            Dict containing the API response.
        """
        url = f"{self.base_url}/chat/completions"
        
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream
        }
        
        if web_search:
            payload["web_search"] = True
        
        if max_tokens:
            payload["max_tokens"] = max_tokens
        
        try:
            if stream:
                return self._stream_request(url, payload)
            else:
                response = requests.post(url, headers=self.headers, json=payload, timeout=60)
                response.raise_for_status()
                return response.json()
        except requests.exceptions.RequestException as e:
            return {"error": str(e)}


def main_test():
    """Example usage of the DeepSeek client."""
    # Initialize the client
    try:
        client = DeepSeekClient()
    except ValueError as e:
        print(f"Error: {e}")
        print("\nPlease set your API key:")
        print("  export DEEPSEEK_API_KEY='your-api-key-here'")
        return
    
    # Example 1: Simple question with web search
    print("=" * 80)
    print("Example 1: Asking a question with web search enabled")
    print("=" * 80)
    
    question = "What are the latest developments in AI as of October 2025?"
    print(f"\nQuestion: {question}\n")
    
    response = client.search_and_ask(
        question=question,
        web_search=True,
        temperature=0.7
    )
    
    if "error" in response:
        print(f"Error: {response['error']}")
    else:
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No response")
        print(f"Answer: {answer}\n")
    
    # Example 2: Streaming response
    print("=" * 80)
    print("Example 2: Streaming response with web search")
    print("=" * 80)
    
    question2 = "What's the weather like in major cities today?"
    print(f"\nQuestion: {question2}\n")
    print("Answer (streaming): ", end='')
    
    response2 = client.search_and_ask(
        question=question2,
        web_search=True,
        stream=True,
        temperature=0.7
    )
    
    # Example 3: Multi-turn conversation
    print("\n" + "=" * 80)
    print("Example 3: Multi-turn conversation")
    print("=" * 80)
    
    messages = [
        {"role": "user", "content": "What is Python?"},
        {"role": "assistant", "content": "Python is a high-level programming language..."},
        {"role": "user", "content": "What are its main uses?"}
    ]
    
    print(f"\nConversation history: {len(messages)} messages")
    print(f"Latest question: {messages[-1]['content']}\n")
    
    response3 = client.chat(
        messages=messages,
        temperature=0.7
    )
    
    if "error" in response3:
        print(f"Error: {response3['error']}")
    else:
        answer = response3.get("choices", [{}])[0].get("message", {}).get("content", "No response")
        print(f"Answer: {answer}\n")


if __name__ == "__main__":
    main_test()
