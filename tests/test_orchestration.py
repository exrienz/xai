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
                {"name": "Agent1", "role": "Role1"},
                {"name": "Agent2", "role": "Role2"}
            ]
        }

        mock_call_openwebui.return_value = json.dumps(mock_plan)

        plan = await step1_plan("Test question")
        self.assertEqual(len(plan["agents"]), 2)
        self.assertEqual(plan["agents"][0]["name"], "Agent1")

    @patch("main.call_openwebui")
    async def test_step2_execute_runs_agents(self, mock_call_openwebui):
        agents = [
            {"name": "Agent1", "role": "Role1"},
            {"name": "Agent2", "role": "Role2"}
        ]

        # Mock individual agent responses
        mock_call_openwebui.return_value = "Response 1"

        responses, agent_models = await step2_execute(agents, "Test question")
        self.assertIn("Agent1", responses)
        self.assertIn("Agent2", responses)
        self.assertIn("Agent1", agent_models)
        self.assertIn("Agent2", agent_models)

    @patch("main.call_openwebui")
    async def test_step3_synthesize_constructs_output(self, mock_call_openwebui):
        plan = {
            "agents": [
                {"name": "Agent1", "role": "Role1"}
            ]
        }
        responses = {"Agent1": "Response 1"}
        agent_models = {"Agent1": "test-model"}

        mock_call_openwebui.return_value = "Final Answer"

        final = await step3_synthesize("Test question", plan, responses, agent_models)

        # step3_synthesize returns the full output with roster, responses, and synthesis
        self.assertIn("## 1. Agent Roster", final)
        self.assertIn("## 2. Individual Agent Responses", final)
        self.assertIn("## 3. Synthesis & Final Verdict", final)
        self.assertIn("Final Answer", final)
        self.assertIn("Agent1", final)
        self.assertIn("Role1", final)
        self.assertIn("test-model", final)

if __name__ == '__main__':
    unittest.main()
