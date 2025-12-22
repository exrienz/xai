# Multi-Agent AI Orchestrator

A powerful FastAPI-based application that coordinates a team of specialized AI agents to answer complex user questions. The system uses a primary orchestrator to analyze queries, plan a team of expert agents, execute them in parallel, and synthesize a final comprehensive answer.

## 🚀 Features

- **Intelligent Orchestration**: Analyzes questions to determine the necessary domains and agent roles.
- **Multi-Agent Collaboration**: Spawns 3-9 specialized agents (e.g., Medical Expert, Legal Advisor, Technical Analyst) to reason independently.
- **Parallel Execution**: Runs agent tasks concurrently for faster response times.
- **Robust Fallback System**: Automatically switches to backup models if the primary model fails or refuses a request.
- **Censorship Detection**: Detects and handles refusals/censorship from models.
- **Dual Interface**:
  - **Web UI**: Clean, responsive interface for direct interaction.
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

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.
