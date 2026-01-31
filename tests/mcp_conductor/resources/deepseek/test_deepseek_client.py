import unittest

from mcp_conductor.resources.deepseek.rest_api import DeepSeekClient


class TestDeepSeekClient(unittest.TestCase):
    def setUp(self):
        self.client = DeepSeekClient()

    def test_search_and_ask(self, ):
        """This unit-test is to test search and ask fucntion for deepseek client
        """
        question = "Help me solve equation: 2x + 1 = 3, please tell me the value of x. "
        print(f"\nQuestion: {question}")
        print("\nSearching the web and generating answer...\n")
        print("-" * 80)

        response = self.client.search_and_ask(
            question=question,
            web_search=True,
            temperature=0.7,
            stream=False
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