import unittest
import re

from mcp_conductor.ai_platforms.sisi.rest_api import SISIClient


class TestSISIClient(unittest.TestCase):
    def setUp(self):
        self.client = SISIClient()
    
    def test_search_and_ask(self, ):
        """This unit-test is to test search and ask fucntion for sisi client
        """
        question = "请帮我总结下面这段英文内容。其中包括了气象与新闻，请总结并翻译中文并只输出中文内容。"
        english_content = "Today is 35 degree. Everything is good aroud the world, no bad news."
        question += english_content
        print(f"\nQuestion: {question}")
        print("\nSearching the web and generating answer...\n")
        print("-" * 80)

        response = self.client.search_and_ask(
            question=question,
            temperature=0.7
        )
        
        # assert if get error response
        self.assertIsInstance(response, dict, msg="Response is not a dict")
        self.assertNotIn("error", response, msg=f"DeepSeek API error: {response.get('error')}")
        
        # Extract and display the answer
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No response")
        print(answer)
        print("-" * 80)
        
        # Show usage information if available
        if "usage" in response:
            usage = response["usage"]
            print(f"\nTokens used: {usage.get('total_tokens', 'N/A')}")
        
        print("\n✓ Success!")
    
    def test_sisi_pipe_detector(self, ):
        question = """
        你有监控霍尔木兹海峡、马六甲、巴拿马等关键通道的拥堵、封锁、延误情况的能力吗？回答有或没有。
        """
        # question += english_content
        print(f"\nQuestion: {question}")
        print("\nSearching the web and generating answer...\n")
        print("-" * 80)

        response = self.client.search_and_ask(
            question=question,
            temperature=0.5
        )
        
        # assert if get error response
        self.assertIsInstance(response, dict, msg="Response is not a dict")
        self.assertNotIn("error", response, msg=f"DeepSeek API error: {response.get('error')}")
        
        # Extract and display the answer
        answer = response.get("choices", [{}])[0].get("message", {}).get("content", "No response")
        answer = re.sub(r'<think>.*?</think>', '', answer, flags=re.DOTALL).strip()
        print(answer)
        print("-" * 80)
        
        # Show usage information if available
        if "usage" in response:
            usage = response["usage"]
            print(f"\nTokens used: {usage.get('total_tokens', 'N/A')}")
        
        print("\n✓ Success!")