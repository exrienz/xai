Multi-Model AI Response Fusion API
====================================

This project provides a FastAPI-based service that queries multiple AI models through the Cerebras API, then uses a judge model to synthesize the best response from all models.

## Features

- Queries 3 AI models simultaneously for each user question
- Uses a judge model to synthesize responses into a final answer
- Secure API key authentication
- Fully containerized with Docker
- Health check endpoint
- Async processing for optimal performance

## Architecture

1. User submits question via /ask endpoint with authentication
2. System queries 3 models concurrently (MODEL1, MODEL2, MODEL3)
3. Judge model analyzes all responses and creates synthesized answer
4. Returns input, individual model responses, and judge's final answer

## API Endpoints

POST /ask
- Requires "code-x-key" header for authentication
- Request body: {"question": "string", "system_message": "string"}
- Returns synthesized response with reasoning

GET /health
- Health check endpoint

## Models Used

Main Models:
- qwen-3-235b-a22b-instruct-2507
- gpt-oss-120b  
- llama-4-maverick-17b-128e-instruct

Judge Model:
- qwen-3-235b-a22b-thinking-2507

## Setup

1. Create .env file with required environment variables:
   CEREBRAS_API_KEY=your_api_key_here
   CODE_X_KEY=your_custom_api_key_here
   MODEL1=qwen-3-235b-a22b-instruct-2507
   MODEL2=gpt-oss-120b
   MODEL3=llama-4-maverick-17b-128e-instruct
   JUDGE=qwen-3-235b-a22b-thinking-2507
   MAX_TOKENS=1024

2. Run with Docker Compose:
   docker-compose up --build

3. Or run with Docker:
   docker build -t xai-app .
   docker run -p 2000:2000 --env-file .env xai-app

4. Or run locally:
   pip install -r requirements.txt
   python main.py

## Usage

The service runs on port 2000. Example API call:

curl -X POST "http://localhost:2000/ask" \
  -H "Content-Type: application/json" \
  -H "code-x-key: your_custom_api_key_here" \
  -d '{"question": "What is quantum computing?"}'

## Response Format

{
  "input": "What is quantum computing?",
  "models": {
    "MODEL1": "response from model 1",
    "MODEL2": "response from model 2", 
    "MODEL3": "response from model 3"
  },
  "judge": {
    "final_answer": "synthesized response combining best aspects",
    "reasoning": "explanation of synthesis process"
  }
}

## Dependencies

- FastAPI 0.104.1
- Uvicorn 0.24.0
- HTTPX 0.25.2
- Python-dotenv 1.0.0
- Pydantic 2.5.0

## Security

- API key authentication required
- Environment variables for sensitive data
- No secrets hardcoded in source code

## Health Monitoring

Built-in health check at /health endpoint with Docker health check configuration.