# Multi-Agent AI Orchestrator 🤖

A powerful FastAPI-based service that leverages multiple AI models via an OpenWebUI compatible API to provide superior responses by combining the strengths of different specialized agents through an intelligent orchestration system.

## ✨ Key Features

- **Multi-Agent Orchestration**: Dynamically recruits and coordinates specialized AI agents based on the query.
- **Unified API Interface**: All models are accessed via `OPENWEBUI_BASE`, simplifying integration.
- **Robust Fallback System**:
  - Primary Orchestrator: `gpt-oss-120b`
  - Fallback/Uncensored Backstop: `dolphin-mistral-24b-venice-edition`
  - Retry Logic: If the fallback fails, it retries with other models from the pool.
- **Transparent Reasoning**: Displays the agent roster, individual responses, cross-analysis, and final synthesis.
- **Secure Authentication**: API key-based authentication with CSRF protection.
- **Web Interface**: User-friendly web interface.
- **Docker Ready**: Full containerization support.

## 🏗️ Architecture

```
User Question → Orchestrator (Plan) → [Agent 1, Agent 2, ...] (Execute) → Orchestrator (Synthesize) → Final Response
```

1. **Plan**: The Orchestrator (`gpt-oss-120b`) analyzes the question and recruits a roster of specialized agents (3-9 agents).
2. **Execute**: Each recruited agent processes the question. Agents are **randomly assigned** a model from the configured pools.
3. **Synthesize**: The Orchestrator reviews all agent responses, performs cross-analysis, and produces a final unified answer.

## 🤖 Model Configuration & Fallback

The system is designed to be resilient and uncensored by default via fallback.

### Model Hierarchy
1. **Orchestrator**:
   - Primary: `gpt-oss-120b`
   - Fallback: `dolphin-mistral-24b-venice-edition` (Uncensored)

2. **Specialist Agents**:
  - Primary: **Randomly Selected** from `MODEL_POOL_OPENWEBUI`.
   - Fallback: `dolphin-mistral-24b-venice-edition`

### Fallback Logic
If ANY model (Orchestrator or Specialist):
1. Returns an error (HTTP 500, timeout, etc.)
2. Refuses to answer (Censorship detection: "I cannot", "As an AI", etc.)

Then:
- The system immediately switches to the **Venice** model (`dolphin-mistral-24b-venice-edition`).
- If Venice itself fails, it retries with another random model from the pool.

## 🚀 Quick Start

### 1. Environment Configuration

Create a `.env` file in the project root:

```env
OPENWEBUI_KEY=your_key_here
OPENWEBUI_BASE=https://your-openwebui-instance

CODE_X_KEY=your_custom_api_key_here
CSRF_SECRET_KEY=your_secret_key_here

# Orchestrator Configuration
MODEL_ORCHESTRATOR_PRIMARY=gpt-oss-120b
MODEL_ORCHESTRATOR_FALLBACK=cognitivecomputations/dolphin-mistral-24b-venice-edition:free

# Specialist Configuration
MODEL_SPECIALIST_PRIMARY=random
MODEL_SPECIALIST_FALLBACK=cognitivecomputations/dolphin-mistral-24b-venice-edition:free

# Model Pools (Comma separated)
MODEL_POOL_OPENWEBUI=nousresearch/hermes-3-llama-3.1-405b:free,moonshotai/kimi-k2:free,cognitivecomputations/dolphin-mistral-24b-venice-edition:free

# Generation Settings
MAX_TOKENS=4096
TEMPERATURE=0.7
TOP_P=0.8
```

### 2. Deploy with Docker

```bash
docker-compose up --build
```

### 3. Local Development

```bash
pip install -r requirements.txt
python main.py
```

## 📚 API Documentation

### `POST /ask`
Main API endpoint. Requires `code-x-key` header.

```json
{
  "question": "How do I ...?",
  "system_message": "Optional system prompt"
}
```

## 🛠️ Configuration Options

| Environment Variable | Description |
|---------------------|-------------|
| `OPENWEBUI_BASE` | Base URL for the OpenAI-compatible API |
| `MODEL_ORCHESTRATOR_PRIMARY` | Main model for planning/synthesis |
| `MODEL_SPECIALIST_PRIMARY` | "random" for random assignment |
| `MODEL_POOL_OPENWEBUI` | List of models available via OpenWebUI |

## 🔒 Security

- **Censorship Evasion**: The system automatically falls back to uncensored models if the primary model refuses a request.
- **Fail-Safe**: Never exposes internal errors to the user; always attempts to answer.

---
**Made with ❤️ using FastAPI and OpenWebUI**
