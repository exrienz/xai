# Multi-Agent AI Orchestrator

A powerful FastAPI-based application that coordinates a team of specialized AI agents to answer complex user questions. The system uses a primary orchestrator to analyze queries, plan a team of expert agents, execute them in parallel, and synthesize a final comprehensive answer.

## 🚀 Features

- **Intelligent Orchestration**: Analyzes questions to determine the necessary domains and agent roles.
- **Multi-Agent Collaboration**: Spawns 3-9 specialized agents (e.g., Medical Expert, Legal Advisor, Technical Analyst) to reason independently.
- **Parallel Execution**: Runs agent tasks concurrently for faster response times.
- **Follow-up Questions**: 🆕 Continue conversations after the final verdict by asking follow-up questions while preserving context.
- **Robust Fallback System**: Automatically switches to backup models if the primary model fails or refuses a request.
- **Censorship Detection**: Detects and handles refusals/censorship from models.
- **Dual Interface**:
  - **Web UI**: Clean, responsive interface for direct interaction with follow-up support.
  - **REST API**: Full JSON API for integration with other apps.
- **Customizable Model Pools**: Configure specific models for orchestrators and specialists via environment variables.

## 🛠️ Prerequisites

- Python 3.9+
- [Git](https://git-scm.com/)
- An OpenWebUI instance (or compatible OpenAI-like API provider)

## 📦 Installation

1.  **Clone the repository:**
    ```bash
    git clone <repository-url>
    cd xai
    ```

2.  **Create a virtual environment:**
    ```bash
    python -m venv venv
    source venv/bin/activate  # On Windows: venv\Scripts\activate
    ```

3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Configure Environment:**
    Copy the example environment file and edit it with your API keys and settings.
    ```bash
    cp .env.example .env
    ```
    
    Update `.env` with your actual credentials:
    ```ini
    OPENWEBUI_KEY=your_actual_api_key
    OPENWEBUI_BASE=https://your-openwebui-instance
    ```

## 🏃 Usage

### Running Locally

Start the development server:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 2000
```

Access the application at: `http://localhost:2000`

### Running with Docker

1.  **Build the image:**
    ```bash
    docker build -t xai-orchestrator .
    ```

2.  **Run the container:**
    ```bash
    docker run -p 2000:2000 --env-file .env xai-orchestrator
    ```
    Or use Docker Compose:
    ```bash
    docker-compose up -d
    ```

## 🔌 API Endpoints

### `POST /ask`
Submits a question to the orchestrator via API.

**Headers:**
- `code-x-key`: (Optional) API key for authentication if configured.

**Request Body:**
```json
{
  "question": "Analyze the potential impact of quantum computing on modern cryptography."
}
```

**Response:**
```json
{
  "input": "...",
  "models": { ... },
  "judge": {
    "final_answer": "Markdown formatted final synthesis...",
    "reasoning": "Multi-Agent Orchestration"
  }
}
```

### `GET /`
Serves the web interface.

### `POST /web-followup`
Submits a follow-up question to continue a conversation.

**Form Data:**
- `question`: The follow-up question
- `conversation_id`: ID of the previous conversation to continue from
- `csrf_token`: CSRF token for security

**Response:**
```json
{
  "response": "Markdown formatted answer with preserved context...",
  "conversation_id": "new-conversation-uuid",
  "parent_conversation_id": "parent-conversation-uuid"
}
```

### `GET /conversation/{conversation_id}`
Retrieve the full history of a conversation.

**Response:**
```json
{
  "id": "conversation-uuid",
  "messages": [
    {"role": "user", "content": "...", "timestamp": "..."},
    {"role": "assistant", "content": "...", "timestamp": "..."}
  ],
  "verdict_content": "## 3. Synthesis & Final Verdict\n...",
  "created_at": "...",
  "last_updated": "...",
  "parent_conversation_id": "..."
}
```

## 💬 Follow-up Questions

The application now supports multi-turn conversations with context preservation:

### How It Works

1. **Initial Question**: Submit your question through the web interface or API
2. **Final Verdict**: Once the "## 3. Synthesis & Final Verdict" section is generated, a follow-up input appears
3. **Ask Follow-ups**: Type your follow-up question in the dedicated section below the response
4. **Context Preservation**: The system automatically creates a new conversation seeded with the previous verdict content
5. **Continuous Chain**: Each follow-up creates a new conversation linked to its parent, preserving the conversation chain

### Features

- **Automatic Context Seeding**: Follow-up questions include the previous verdict as context
- **Smart Truncation**: Context is intelligently truncated to prevent excessive prompt growth (configurable via `MAX_CONVERSATION_CONTEXT_LENGTH`)
- **Conversation Chains**: Each follow-up maintains a link to its parent conversation
- **Auto-Cleanup**: Old conversations are automatically removed after 24 hours (configurable via `CONVERSATION_TIMEOUT_HOURS`)
- **Feature Flag**: Can be enabled/disabled via environment variable for safe rollout

### Usage Tips

- Use follow-ups to dive deeper into specific aspects of the answer
- Ask clarifying questions without losing the original context
- Request examples or elaborations on specific points
- **Keyboard Shortcut**: Press `Ctrl+Enter` in the follow-up input to submit

### Limitations

- Context is limited to the "## 3. Synthesis & Final Verdict" section (not the full conversation history)
- Maximum context length is enforced to prevent excessive costs and latency
- Conversations are stored in-memory (will be lost on server restart until database persistence is implemented)

## ⚙️ Configuration

Key environment variables in `.env`:

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENWEBUI_BASE` | Base URL for the LLM API provider | `""` |
| `OPENWEBUI_KEY` | API Key for the LLM provider | `""` |
| `MODEL_ORCHESTRATOR_PRIMARY` | Main model for planning and synthesis | `gpt-oss-120b` |
| `MODEL_POOL_OPENWEBUI` | Comma-separated list of models for agents to use | (List of available models) |
| `MAX_TOKENS` | Max generation tokens per request | `4096` |
| `CODE_X_KEY` | Secret key for API authentication (optional) | `""` |
| `ENABLE_FOLLOWUP_QUESTIONS` | Enable/disable follow-up questions feature | `true` |
| `MAX_CONVERSATION_CONTEXT_LENGTH` | Max characters of context to preserve in follow-ups | `8000` |
| `CONVERSATION_TIMEOUT_HOURS` | Hours before old conversations are auto-cleaned | `24` |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
