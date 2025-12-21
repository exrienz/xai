# Multi-Model AI Response Fusion API 🤖

[![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/python-3670A0?style=for-the-badge&logo=python&logoColor=ffdd54)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/docker-%230db7ed.svg?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)

A powerful FastAPI-based service that leverages multiple AI models through the Cerebras API to provide superior responses by combining the strengths of different specialized agents through an intelligent orchestration system.

## ✨ Key Features

- **Multi-Agent Orchestration**: Dynamically recruits and coordinates specialized AI agents based on the query.
- **Hybrid Model Architecture**: Combines Cerebras-powered orchestration with OpenWebUI-hosted specialist agents.
- **Robust Fallback System**: Automatically switches to uncensored models (Dolphin Mistral) if agents encounter errors or censorship refusals.
- **Transparent Reasoning**: Displays the agent roster, individual responses, cross-analysis, and final synthesis.
- **Secure Authentication**: API key-based authentication with CSRF protection.
- **Web Interface**: User-friendly web interface with real-time processing and Markdown rendering.
- **Full Containerization**: Docker and Docker Compose ready.
- **Async Processing**: High-performance async operations.
- **Comprehensive Logging**: Detailed logging with emojis for better readability.
- **Health Monitoring**: Built-in health check endpoints.

## 🏗️ Architecture

```
User Question → Orchestrator (Plan) → [Agent 1, Agent 2, ...] (Execute) → Orchestrator (Synthesize) → Final Response
```

1. **Plan**: The Orchestrator (`gpt-oss-120b`) analyzes the question and recruits a roster of specialized agents.
2. **Execute**: Each recruited agent processes the question from their specific perspective in parallel. Agents are randomly assigned one of the specialized models. If an agent fails or refuses to answer (censorship), the system automatically retries with a fallback model.
3. **Synthesize**: The Orchestrator reviews all agent responses, performs cross-analysis, and produces a final unified answer.
4. **Output Delivery**: Returns the full transparent reasoning chain and the final answer.

## 🤖 AI Models

### Orchestrator
- **GPT OSS 120B**: `gpt-oss-120b` - Responsible for planning, coordination, and final synthesis.

### Domain Experts (OpenWebUI)
Agents are randomly assigned one of the following models:
- **Dolphin Mistral 24B**: `cognitivecomputations/dolphin-mistral-24b-venice-edition:free` (Also used as Fallback)
- **Hermes 3 Llama 3.1 405B**: `nousresearch/hermes-3-llama-3.1-405b:free`
- **Kimi K2**: `moonshotai/kimi-k2:free`

### Fallback Mechanism
If any model encounters an error or indicates censorship (e.g., "I cannot...", "I am unable..."), the request is automatically retried using **Dolphin Mistral 24B**.

## 🚀 Quick Start

### Prerequisites
- Docker and Docker Compose (recommended)
- Python 3.11+ (for local development)
- Cerebras API key

### 1. Environment Configuration

Create a `.env` file in the project root:

```env
# Cerebras API Configuration
CEREBRAS_API_KEY=your_cerebras_api_key_here
CODE_X_KEY=your_custom_api_key_here

# OpenWebUI Configuration
OPENWEBUI_BASE=https://your-openwebui-instance/api
OPENWEBUI_KEY=your_openwebui_key

# API Settings
MAX_TOKENS=1024
TEMPERATURE=0.7
TOP_P=0.8
STREAM=false
SHOW_MODEL_OUTPUT=false

# Security
CSRF_SECRET_KEY=your_csrf_secret_key_here
```

### 2. Deploy with Docker Compose (Recommended)

```bash
# Clone and navigate to project
git clone <repository-url>
cd xai

# Start the service
docker-compose up --build

# Service will be available at http://localhost:2000
```

### 3. Alternative: Docker

```bash
# Build the image
docker build -t xai-app .

# Run the container
docker run -p 2000:2000 --env-file .env xai-app
```

### 4. Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
```

## 📚 API Documentation

### Authentication
All API endpoints require the `code-x-key` header matching your configured `CODE_X_KEY`.

### Endpoints

#### `POST /ask`
Main API endpoint for processing questions.

**Request:**
```bash
curl -X POST "http://localhost:2000/ask" \
  -H "Content-Type: application/json" \
  -H "code-x-key: your_custom_api_key_here" \
  -d '{
    "question": "What is quantum computing?",
    "system_message": "You are a helpful assistant."
  }'
```

**Response:**
```json
{
  "input": "What is quantum computing?",
  "models": {
    "MODEL1": "Response from Qwen 3 235B...",
    "MODEL2": "Response from GPT OSS 120B...",
    "MODEL3": "Response from Llama 4 Maverick..."
  },
  "judge": {
    "final_answer": "Synthesized response combining the best aspects...",
    "reasoning": "The synthesis process considered..."
  }
}
```

#### `GET /`
Web interface for interactive usage.

#### `POST /web-ask`
Backend endpoint for web interface with CSRF protection.

#### `GET /health`
Health check endpoint.

**Response:**
```json
{
  "status": "healthy"
}
```

## 🛠️ Configuration Options

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `CEREBRAS_API_KEY` | Cerebras API key | Required |
| `OPENWEBUI_BASE` | Base URL for OpenWebUI API | Required |
| `OPENWEBUI_KEY` | API Key for OpenWebUI | Required |
| `CODE_X_KEY` | Custom API key for authentication | Required |
| `MAX_TOKENS` | Maximum tokens per response | 1024 |
| `TEMPERATURE` | Model temperature | 0.7 |
| `TOP_P` | Top-p sampling | 0.8 |
| `STREAM` | Enable streaming responses | false |
| `SHOW_MODEL_OUTPUT` | Include individual model responses in API output | false |
| `CSRF_SECRET_KEY` | CSRF protection secret | Auto-generated |

## 🔒 Security Features

- **API Key Authentication**: Secure access control
- **CSRF Protection**: Web interface protected against cross-site request forgery
- **Environment-based Secrets**: No hardcoded credentials
- **Request Validation**: Input validation with Pydantic models
- **Error Handling**: Comprehensive error handling without information leakage

## 📊 Monitoring & Logging

The application provides comprehensive logging with emoji indicators:
- 🤖 AI model requests
- ✅ Successful responses
- ❌ Error conditions
- 👨‍⚖️ Judge processing
- 🌐 Web interface requests
- 🔐 Security events

## 🐳 Docker Configuration

### Dockerfile
- Based on Python 3.11 slim image
- Multi-stage build for optimization
- Health check included
- Non-root user execution

### Docker Compose
- Service orchestration
- Environment file integration
- Port mapping and health checks
- Easy scaling configuration

## 🧪 Development

### Project Structure
```
xai/
├── main.py              # Main FastAPI application
├── templates/           # Jinja2 templates
│   └── index.html      # Web interface
├── requirements.txt     # Python dependencies
├── Dockerfile          # Container configuration
├── docker-compose.yml  # Service orchestration
├── .env.example        # Environment template
└── README.md          # This file
```

### Dependencies
- **FastAPI 0.104.1**: Modern web framework
- **Uvicorn 0.24.0**: ASGI server
- **HTTPX 0.25.2**: HTTP client for API calls
- **Pydantic**: Data validation
- **Cerebras Cloud SDK**: AI model integration
- **Jinja2**: Template engine
- **python-dotenv**: Environment management

### Running Tests
```bash
# Add your test commands here
# Example: pytest tests/
```

### Code Quality
```bash
# Linting
# Add your linting commands here

# Type checking
# Add your type checking commands here
```

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

## 🆘 Support

For support and questions:
- Create an issue in the GitHub repository
- Check the logs for detailed error information
- Ensure your environment variables are properly configured

## 🎯 Roadmap

- [ ] Support for additional AI model providers
- [ ] Response caching system
- [ ] Advanced analytics and metrics
- [ ] Rate limiting and quota management
- [ ] Webhook support for notifications
- [ ] Multi-language support

---

**Made with ❤️ using FastAPI and Cerebras AI**
