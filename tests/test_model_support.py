import unittest
import json
import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from main import call_openwebui, extract_json_from_text, MAX_TOKENS, TEMPERATURE, TOP_P

# We need to stub extract_json_from_text first as it is not yet in main.py,
# but we will add it. For now, the test will fail if I run it before adding the function,
# but I can define the test structure.
# Actually, I should probably add the function to main.py first or define it in the test file
# temporarily if I were isolating, but since I am modifying main.py, I will add the tests
# expecting the function to exist.

class TestModelSupport(unittest.IsolatedAsyncioTestCase):

    @patch("main.httpx.AsyncClient")
    async def test_call_openwebui_standard_model(self, mock_client_cls):
        # Setup mock
        mock_client = MagicMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Standard Response"}}]
        }
        mock_client.post = AsyncMock(return_value=mock_response)

        # Call with standard model
        await call_openwebui("gpt-4o", [{"role": "user", "content": "hi"}], json_mode=False)

        # Verify payload
        call_args = mock_client.post.call_args
        self.assertIsNotNone(call_args)
        kwargs = call_args.kwargs
        payload = kwargs["json"]

        self.assertEqual(payload["model"], "gpt-4o")
        self.assertEqual(payload["temperature"], TEMPERATURE)
        self.assertEqual(payload["top_p"], TOP_P)
        self.assertEqual(payload["max_tokens"], MAX_TOKENS)
        self.assertNotIn("max_completion_tokens", payload)

    @patch("main.httpx.AsyncClient")
    async def test_call_openwebui_thinking_model(self, mock_client_cls):
        # Setup mock
        mock_client = MagicMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Thinking Response"}}]
        }
        mock_client.post = AsyncMock(return_value=mock_response)

        # Call with thinking model (e.g. o1-preview)
        await call_openwebui("o1-preview", [{"role": "user", "content": "hi"}], json_mode=False)

        # Verify payload
        call_args = mock_client.post.call_args
        self.assertIsNotNone(call_args)
        kwargs = call_args.kwargs
        payload = kwargs["json"]

        self.assertEqual(payload["model"], "o1-preview")
        # Should NOT have temperature or top_p
        self.assertNotIn("temperature", payload)
        self.assertNotIn("top_p", payload)
        # Should use max_completion_tokens
        self.assertEqual(payload["max_completion_tokens"], MAX_TOKENS)
        self.assertNotIn("max_tokens", payload)

    @patch("main.httpx.AsyncClient")
    async def test_call_openwebui_thinking_model_system_prompt(self, mock_client_cls):
        # Test that system prompt is merged into user prompt or handled
        mock_client = MagicMock()
        mock_client_cls.return_value.__aenter__.return_value = mock_client
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Response"}}]
        }
        mock_client.post = AsyncMock(return_value=mock_response)

        messages = [
            {"role": "system", "content": "System instruction"},
            {"role": "user", "content": "User question"}
        ]

        await call_openwebui("o3-mini", messages, json_mode=False)

        call_args = mock_client.post.call_args
        payload = call_args.kwargs["json"]
        sent_messages = payload["messages"]

        # Expectation: System message should be converted to user or merged
        # Checking if the first message is user and contains system instruction
        self.assertEqual(sent_messages[0]["role"], "user")
        self.assertIn("System instruction", sent_messages[0]["content"])

    def test_extract_json_from_text(self):
        # 1. Clean JSON
        text1 = '{"key": "value"}'
        self.assertEqual(extract_json_from_text(text1), {"key": "value"})

        # 2. Markdown JSON
        text2 = 'Here is the plan:\n```json\n{"key": "value"}\n```'
        self.assertEqual(extract_json_from_text(text2), {"key": "value"})

        # 3. Thinking trace before JSON
        text3 = '<thought>Thinking...</thought>\n{"key": "value"}'
        self.assertEqual(extract_json_from_text(text3), {"key": "value"})

        # 4. Dirty text
        text4 = 'Sure! {"key": "value"} is the answer.'
        self.assertEqual(extract_json_from_text(text4), {"key": "value"})

        # 5. Invalid JSON
        text5 = 'No json here'
        self.assertIsNone(extract_json_from_text(text5))

if __name__ == '__main__':
    unittest.main()
