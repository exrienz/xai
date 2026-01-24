# Multi-Agent AI Orchestrator

A powerful FastAPI-based application that coordinates a team of specialized AI agents to answer complex user questions. The system uses a primary orchestrator to analyze queries, plan a team of expert agents, execute them in parallel, and synthesize a final comprehensive answer.

## 🚀 Features

- **Intelligent Orchestration**: Analyzes questions to determine the necessary domains and agent roles.
- **Multi-Agent Collaboration**: Spawns 3-9 specialized agents (e.g., Medical Expert, Legal Advisor, Technical Analyst) to reason independently.
- **Parallel Execution**: Runs agent tasks concurrently for faster response times.
- **Async URL Responses**: 🆕 Get a unique, shareable URL immediately when submitting questions. Results persist for 30 days and can be accessed anytime.
- **Follow-up Questions**: Continue conversations after the final verdict by asking follow-up questions while preserving context.
- **Robust Fallback System**: Automatically switches to backup models if the primary model fails or refuses a request.
- **Censorship Detection**: Detects and handles refusals/censorship from models.
- **Dual Interface**:
  - **Web UI**: Clean, responsive interface with async mode toggle and real-time status updates.
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

## 🔗 Async URL Responses (v1.2.0)

The application now supports asynchronous job processing with persistent, shareable URLs:

### How It Works

1. **Enable Async Mode**: Check the "Async Mode" toggle in the web interface (enabled by default)
2. **Submit Question**: Click "Ask Question" - you'll immediately receive a unique URL
3. **Get Shareable URL**: Copy the URL and share it, bookmark it, or leave the page
4. **Real-time Updates**: The page automatically polls for status updates (queued → running → completed/failed)
5. **Persistent Results**: Results are stored for 30 days and accessible anytime via the unique URL
6. **Retry on Failure**: If a job fails, you can retry it with a single click

### Features

- **Immediate Response**: Get a unique URL within seconds, no need to wait for completion
- **30-Day Retention**: All results are accessible for 30 days after creation
- **Shareable URLs**: Send the URL to colleagues or save it for later reference
- **Automatic Cleanup**: Expired results are automatically deleted after 30 days
- **Real-time Status**: Live status updates (queued, running, completed, failed) with automatic polling
- **Retry Mechanism**: Failed jobs can be retried without resubmitting the question
- **Concurrent Processing**: Background job processing doesn't block the web server
- **Expiration Handling**: Expired URLs return a user-friendly 410 Gone response

### API Endpoints

#### Submit Async Job
```bash
POST /web-ask-async
Content-Type: multipart/form-data

question=Your+question+here&csrf_token=...

Response:
{
  "url_slug": "a1b2c3d4e5f6",
  "result_url": "/result/a1b2c3d4e5f6",
  "status": "queued",
  "created_at": "2024-01-24T12:00:00",
  "expires_at": "2024-02-23T12:00:00"
}
```

#### Get Job Status/Result
```bash
GET /api/result/{url_slug}

Response (while processing):
{
  "url_slug": "a1b2c3d4e5f6",
  "question": "Your question",
  "status": "running",
  "response_content": null,
  "error_message": null,
  "created_at": "2024-01-24T12:00:00",
  "started_at": "2024-01-24T12:00:05",
  "completed_at": null,
  "expires_at": "2024-02-23T12:00:00",
  "last_updated": "2024-01-24T12:00:05"
}

Response (completed):
{
  "url_slug": "a1b2c3d4e5f6",
  "question": "Your question",
  "status": "completed",
  "response_content": "## 1. Agent Roster\n...",
  "created_at": "2024-01-24T12:00:00",
  "completed_at": "2024-01-24T12:01:30",
  "expires_at": "2024-02-23T12:00:00",
  ...
}

Response (expired):
410 Gone
{
  "detail": "This result has expired. Results are retained for 30 days."
}
```

#### Retry Failed Job
```bash
POST /api/result/{url_slug}/retry
Content-Type: multipart/form-data

csrf_token=...

Response:
{
  "status": "retry_initiated",
  "url_slug": "a1b2c3d4e5f6"
}
```

#### Job Statistics (Monitoring)
```bash
GET /admin/job-stats

Response:
{
  "queued": 5,
  "running": 2,
  "completed": 150,
  "failed": 3,
  "total": 160
}
```

### Usage Tips

- **Long-running Queries**: Use async mode for complex questions that might take a while
- **Sharing Results**: Share the URL with team members without waiting for completion
- **Bookmark Important Answers**: Save the URL for future reference (valid for 30 days)
- **Offline Processing**: Submit a question and come back later to see the result
- **Sync Mode**: Disable async mode if you prefer traditional blocking behavior

### Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `ENABLE_ASYNC_JOBS` | Enable/disable async job processing | `true` |
| `ASYNC_JOB_RETENTION_DAYS` | Days before jobs expire and are deleted | `30` |
| `DATABASE_URL` | Database connection string | `sqlite+aiosqlite:///./xai_async_jobs.db` |
| `SQL_DEBUG` | Enable SQL query logging | `false` |

### Database

Async jobs are stored in a SQLite database (or PostgreSQL in production). The database is automatically initialized on startup.

**Schema:**
- `async_jobs` table with columns: id, url_slug, question, status, response_content, error_message, conversation_id, created_at, started_at, completed_at, expires_at, last_updated
- Automatic cleanup task runs every hour to remove expired jobs

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
| `ENABLE_ASYNC_JOBS` | Enable/disable async job processing with persistent URLs | `true` |
| `ASYNC_JOB_RETENTION_DAYS` | Days before async job results expire | `30` |
| `DATABASE_URL` | Database connection string for async jobs | `sqlite+aiosqlite:///./xai_async_jobs.db` |
| `SQL_DEBUG` | Enable SQL query logging for debugging | `false` |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
