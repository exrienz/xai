import os
import asyncio
import re
import logging
import secrets
import time
import json
import random
import httpx
from typing import Dict, Any, List
from fastapi import FastAPI, HTTPException, Header, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pydantic import BaseModel
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from system_prompts import MASTER_SYSTEM_PROMPT, PLANNING_PROMPT

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

OPENWEBUI_MODELS = [
    "cognitivecomputations/dolphin-mistral-24b-venice-edition:free",
    "nousresearch/hermes-3-llama-3.1-405b:free",
    "moonshotai/kimi-k2:free"
]
FALLBACK_MODEL = "cognitivecomputations/dolphin-mistral-24b-venice-edition:free"
ORCHESTRATOR_MODEL = "gpt-oss-120b"

app = FastAPI(title="Multi-Agent AI Orchestrator", version="1.0.0")
client = Cerebras(api_key=os.environ.get("CEREBRAS_API_KEY"))
templates = Jinja2Templates(directory="templates")

# CSRF Protection
CSRF_SECRET_KEY = os.getenv("CSRF_SECRET_KEY", secrets.token_hex(32))
csrf_serializer = URLSafeTimedSerializer(CSRF_SECRET_KEY)

def generate_csrf_token() -> str:
    """Generate a CSRF token"""
    return csrf_serializer.dumps({"timestamp": time.time()})

def validate_csrf_token(token: str, max_age: int = 3600) -> bool:
    """Validate a CSRF token (expires after max_age seconds)"""
    try:
        csrf_serializer.loads(token, max_age=max_age)
        return True
    except Exception:
        return False

class QuestionRequest(BaseModel):
    question: str
    system_message: str = ""

class ModelResponse(BaseModel):
    input: str
    models: Dict[str, str] = None
    judge: Dict[str, str]

class WebQuestionRequest(BaseModel):
    question: str

class WebResponse(BaseModel):
    response: str

async def verify_api_key(code_x_key: str = Header(..., alias="code-x-key")):
    expected_key = os.getenv("CODE_X_KEY")
    if not expected_key:
        raise HTTPException(status_code=500, detail="API key not configured")
    if code_x_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return code_x_key

def is_censored(text: str) -> bool:
    """Check if the response text indicates censorship/refusal."""
    censorship_phrases = [
        "I cannot", "I am unable", "I'm sorry", "As an AI",
        "I can't", "cannot fulfill", "cannot comply", "against my programming"
    ]
    # Check mostly beginning of response
    lower_text = text[:200].lower()
    for phrase in censorship_phrases:
        if phrase.lower() in lower_text:
            return True
    return False

async def call_openwebui(model: str, messages: List[Dict[str, str]], json_mode: bool) -> str:
    api_base = os.getenv("OPENWEBUI_BASE", "")
    api_key = os.getenv("OPENWEBUI_KEY", "")

    if not api_base:
        raise ValueError("OPENWEBUI_BASE not set")

    # Construct URL assuming OpenAI compatible endpoint if not specified
    if "chat/completions" not in api_base:
        url = f"{api_base.rstrip('/')}/chat/completions"
        # Some users might set base to .../v1
        if "/v1" not in api_base and "/api" not in api_base:
             # Heuristic: try adding /api/chat/completions if it looks like a bare host
             # But let's stick to standard append for now
             pass
    else:
        url = api_base

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": float(os.getenv("TEMPERATURE", "0.7")),
        "top_p": float(os.getenv("TOP_P", "0.8"))
    }

    if json_mode:
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient() as http_client:
        response = await http_client.post(url, headers=headers, json=payload, timeout=60.0)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]

async def call_model(model: str, user_input: str, system_message: str = "", json_mode: bool = False, attempt_fallback: bool = True) -> str:
    # Increase max tokens for complex reasoning
    max_tokens = int(os.getenv("MAX_TOKENS", "4096"))
    temperature = float(os.getenv("TEMPERATURE", "0.7"))
    top_p = float(os.getenv("TOP_P", "0.8"))
    
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": user_input})
    
    logger.info(f"🤖 AI REQUEST - Model: {model}")
    
    try:
        content = ""
        if model in OPENWEBUI_MODELS or model == FALLBACK_MODEL:
            content = await call_openwebui(model, messages, json_mode)
        else:
            # Default to Cerebras for others (gpt-oss-120b)
            response_format = {"type": "json_object"} if json_mode else None
            chat_completion = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stream=False,
                response_format=response_format
            )
            content = chat_completion.choices[0].message.content

        if content is None:
            logger.warning(f"⚠️ Model {model} returned None content.")
            content = ""
            
        # Check for censorship
        if attempt_fallback and model != FALLBACK_MODEL and is_censored(content):
            logger.warning(f"🚫 Model {model} censored. Falling back to {FALLBACK_MODEL}")
            return await call_model(FALLBACK_MODEL, user_input, system_message, json_mode, attempt_fallback=False)

        logger.info(f"✅ AI RESPONSE - Model: {model} - Length: {len(content)} chars")
        return content

    except Exception as e:
        logger.error(f"❌ AI REQUEST FAILED - Model: {model} Error: {str(e)}")

        if attempt_fallback and model != FALLBACK_MODEL:
            logger.warning(f"🔄 Error with {model}. Falling back to {FALLBACK_MODEL}")
            return await call_model(FALLBACK_MODEL, user_input, system_message, json_mode, attempt_fallback=False)

        # Don't raise immediately, allow fallback handling in caller if possible,
        # but here we just raise to be caught by specific steps
        raise HTTPException(status_code=500, detail=f"Error calling {model}: {str(e)}")

async def step1_plan(question: str) -> Dict[str, Any]:
    """Call Orchestrator to plan agents."""
    logger.info("📋 ORCHESTRATOR PLANNING START")
    try:
        response = await call_model(
            "gpt-oss-120b",
            question,
            system_message=PLANNING_PROMPT,
            json_mode=True
        )
        if not response:
            raise ValueError("Empty response from planner")

        plan = json.loads(response)
        logger.info(f"📋 ORCHESTRATOR PLAN: {plan}")
        return plan
    except json.JSONDecodeError:
        logger.error("Failed to parse JSON plan")
        return {"reasoning": "Failed to parse plan", "agents": []}
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        return {"reasoning": f"Planning failed: {str(e)}", "agents": []}

async def step2_execute(agents: List[Dict[str, str]], question: str) -> Dict[str, str]:
    """Execute agents in parallel."""
    logger.info(f"🚀 EXECUTING {len(agents)} AGENTS")
    
    tasks = []
    agent_names = []
    
    for agent in agents:
        name = agent.get("name", "Unknown Agent")
        role = agent.get("role", "Helpful Assistant")

        # Randomly select a specialist agent model
        model = random.choice(OPENWEBUI_MODELS)
        logger.info(f"🎯 Assigned model {model} to agent {name}")

        agent_names.append(name)

        system_msg = f"You are {name}. Role: {role}. Question: {question}. Answer concisely and professionally."

        # call_model handles fallback if error or censored
        tasks.append(call_model(model, question, system_message=system_msg))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    responses = {}
    for name, result in zip(agent_names, results):
        if isinstance(result, Exception):
            responses[name] = f"Error: {str(result)}"
        elif not result:
             # Fallback if result is empty string (None content)
            responses[name] = "Error: No response from model."
        else:
            responses[name] = result
    
    # Check for failures and retry with fallback if needed
    # (Optional: Implement retry with gpt-oss-120b if allowed, but strict mode says no.
    # However, to make the app usable, we might want to.)
    
    logger.info(f"✅ AGENT EXECUTION COMPLETE")
    return responses

async def step3_synthesize(question: str, plan: Dict[str, Any], agent_responses: Dict[str, str]) -> str:
    """Synthesize final response using Orchestrator."""
    logger.info("👨‍⚖️ ORCHESTRATOR SYNTHESIS START")
    
    agent_roster_str = "\n".join([f"- {a['name']} ({a['model']}): {a['role']}" for a in plan.get("agents", [])])
    agent_responses_str = "\n\n".join([f"### {name}\n{resp}" for name, resp in agent_responses.items()])
    
    synthesis_input = f"""
User Question: {question}

Agent Roster:
{agent_roster_str}

Agent Responses:
{agent_responses_str}

Please produce the final output following the 'Output Transparency' rules in the system prompt.
Must include Agent Roster, Individual Agent Responses, Cross-Analysis, and Final Answer.
"""
    
    response = await call_model("gpt-oss-120b", synthesis_input, system_message=MASTER_SYSTEM_PROMPT)
    return response

async def orchestrate(question: str) -> Dict[str, Any]:
    # Step 1: Plan
    plan = await step1_plan(question)
    
    # Step 2: Execute
    agents = plan.get("agents", [])
    if not agents:
        # Trivial case or fallback
        logger.info("ℹ️ No agents needed or planning failed. Direct answer.")
        direct_response = await call_model("gpt-oss-120b", question, system_message=MASTER_SYSTEM_PROMPT)
        return {
            "final_answer": direct_response,
            "models": {},
            "plan": plan
        }
    
    agent_responses = await step2_execute(agents, question)
    
    # Step 3: Synthesize
    final_output = await step3_synthesize(question, plan, agent_responses)
    
    return {
        "final_answer": final_output,
        "models": agent_responses,
        "plan": plan
    }

@app.post("/ask", response_model=ModelResponse)
async def ask_question(
    request: QuestionRequest,
    api_key: str = Depends(verify_api_key)
):
    try:
        result = await orchestrate(request.question)
        
        return ModelResponse(
            input=request.question,
            models=result["models"],
            judge={
                "final_answer": result["final_answer"],
                "reasoning": "Multi-Agent Orchestration"
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    csrf_token = generate_csrf_token()
    return templates.TemplateResponse("index.html", {
        "request": request,
        "csrf_token": csrf_token
    })

@app.post("/web-ask", response_model=WebResponse)
async def web_ask_question(
    question: str = Form(...),
    csrf_token: str = Form(...)
):
    if not validate_csrf_token(csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    
    try:
        result = await orchestrate(question)
        return WebResponse(response=result["final_answer"])
    except Exception as e:
        logger.error(f"Web error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=2000)
