
import unittest
import json
import asyncio
from unittest.mock import MagicMock, patch
from main import step1_plan, step2_execute, step3_synthesize

class TestOrchestration(unittest.IsolatedAsyncioTestCase):

    @patch("main.client")
    async def test_step1_plan_creates_agents(self, mock_client):
        # Mock the planner response
        mock_plan = {
            "reasoning": "Test reasoning",
            "agents": [
                {"name": "Agent1", "role": "Role1", "model": "Specialist Model"},
                {"name": "Agent2", "role": "Role2", "model": "Specialist Model"}
            ]
        }

        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content=json.dumps(mock_plan)))
        ]

        plan = await step1_plan("Test question")
        self.assertEqual(len(plan["agents"]), 2)
        self.assertEqual(plan["agents"][0]["name"], "Agent1")

    @patch("main.httpx.AsyncClient")
    @patch("main.client")
    @patch.dict("os.environ", {"OPENWEBUI_KEY": "test_key", "OPENWEBUI_BASE": "http://test_base"})
    async def test_step2_execute_runs_agents(self, mock_client, mock_httpx_client):
        agents = [
            {"name": "Agent1", "role": "Role1", "model": "Specialist Model"},
            {"name": "Agent2", "role": "Role2", "model": "Specialist Model"}
        ]

        # Mock OpenWebUI response via httpx
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Response 1"}}]
        }
        mock_response.raise_for_status.return_value = None

        mock_httpx_client_instance = MagicMock()
        mock_httpx_client_instance.post.return_value = mock_response
        mock_httpx_client_instance.__aenter__.return_value = mock_httpx_client_instance
        mock_httpx_client.return_value = mock_httpx_client_instance

        responses = await step2_execute(agents, "Test question")
        self.assertIn("Agent1", responses)
        self.assertIn("Agent2", responses)

    @patch("main.client")
    async def test_step3_synthesize_constructs_output(self, mock_client):
        plan = {
            "agents": [
                {"name": "Agent1", "role": "Role1", "model": "Specialist Model"}
            ]
        }
        responses = {"Agent1": "Response 1"}

        mock_client.chat.completions.create.return_value.choices = [
            MagicMock(message=MagicMock(content="Final Answer"))
        ]

        final = await step3_synthesize("Test question", plan, responses)
        self.assertEqual(final, "Final Answer")

if __name__ == '__main__':
    unittest.main()
