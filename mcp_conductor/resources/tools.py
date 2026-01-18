import os
import re
from dotenv import load_dotenv


def get_token_from_env(key_name: str) -> str:
    load_dotenv()
    api_key = os.getenv(key_name)
    if not api_key:
        raise ValueError("API key must be provided or set in SISI_API_KEY environment variable")
    return api_key


def remove_think_tag(content: str) -> str:
    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
    return content