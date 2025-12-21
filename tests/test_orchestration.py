import unittest
import json
import asyncio
from unittest.mock import MagicMock, patch
from main import step1_plan, step2_execute, step3_synthesize

class TestOrchestration(unittest.IsolatedAsyncioTestCase):

    @patch("main.call_openwebui")
    async def test_step1_plan_creates_agents(self, mock_call_openwebui):
        # Mock the planner response
        mock_plan = {
            "reasoning": "Test reasoning",
            "agents": [
                {"name": "Agent1", "role": "Role1", "model": "zai-glm-4.6"},
                {"name": "Agent2", "role": "Role2", "model": "zai-glm-4.6"}
            ]
        }

        mock_call_openwebui.return_value = json.dumps(mock_plan)

        plan = await step1_plan("Test question")
        self.assertEqual(len(plan["agents"]), 2)
        self.assertEqual(plan["agents"][0]["name"], "Agent1")

    @patch("main.call_openwebui")
    async def test_step2_execute_runs_agents(self, mock_call_openwebui):
        agents = [
            {"name": "Agent1", "role": "Role1", "model": "zai-glm-4.6"},
            {"name": "Agent2", "role": "Role2", "model": "zai-glm-4.6"}
        ]

        # Mock individual agent responses
        mock_call_openwebui.return_value = "Response 1"

        responses = await step2_execute(agents, "Test question")
        self.assertIn("Agent1", responses)
        self.assertIn("Agent2", responses)

    @patch("main.call_openwebui")
    async def test_step3_synthesize_constructs_output(self, mock_call_openwebui):
        plan = {
            "agents": [
                {"name": "Agent1", "role": "Role1", "model": "zai-glm-4.6"}
            ]
        }
        responses = {"Agent1": "Response 1"}

        mock_call_openwebui.return_value = "Final Answer"

        final = await step3_synthesize("Test question", plan, responses)
        self.assertEqual(final, "Final Answer")

if __name__ == '__main__':
    unittest.main()
