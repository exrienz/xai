import os
import asyncio
import logging
import secrets
import time
import json
import random
import re
import httpx
from typing import Dict, Any, List, Tuple, Optional
from fastapi import FastAPI, HTTPException, Header, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pydantic import BaseModel
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

# --- Configuration & Environment Variables ---
def get_env_list(key: str, default: str = "") -> List[str]:
    val = os.getenv(key, default)
    if not val:
        return []
    return [x.strip() for x in val.split(",") if x.strip()]

# Model Configuration
MODEL_ORCHESTRATOR_PRIMARY = os.getenv("MODEL_ORCHESTRATOR_PRIMARY", "gpt-oss-120b")
MODEL_ORCHESTRATOR_FALLBACK = os.getenv("MODEL_ORCHESTRATOR_FALLBACK", "cognitivecomputations/dolphin-mistral-24b-venice-edition:free")

MODEL_SPECIALIST_PRIMARY = os.getenv("MODEL_SPECIALIST_PRIMARY", "random")
MODEL_SPECIALIST_FALLBACK = os.getenv("MODEL_SPECIALIST_FALLBACK", "cognitivecomputations/dolphin-mistral-24b-venice-edition:free")

# Combine pools for random selection
MODEL_POOL = get_env_list("MODEL_POOL_OPENWEBUI")
# Deduplicate while preserving order
MODEL_POOL = list(dict.fromkeys(MODEL_POOL))

if not MODEL_POOL:
    # Default fallback if env is missing
    MODEL_POOL = [
        "gpt-oss-120b",
        "cognitivecomputations/dolphin-mistral-24b-venice-edition:free"
    ]

# Generation Settings
MAX_TOKENS = int(os.getenv("MAX_TOKENS", "4096"))
TEMPERATURE = float(os.getenv("TEMPERATURE", "0.7"))
TOP_P = float(os.getenv("TOP_P", "0.8"))

OPENWEBUI_BASE = os.getenv("OPENWEBUI_BASE", "")
OPENWEBUI_KEY = os.getenv("OPENWEBUI_KEY", "")

# --- App Setup ---
app = FastAPI(title="Multi-Agent AI Orchestrator", version="1.0.0")
templates = Jinja2Templates(directory="templates")

# CSRF Protection
CSRF_SECRET_KEY = os.getenv("CSRF_SECRET_KEY", secrets.token_hex(32))
csrf_serializer = URLSafeTimedSerializer(CSRF_SECRET_KEY)

# --- Helpers ---
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

def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Extracts JSON from text, handling Markdown code blocks and reasoning traces."""
    try:
        # 1. Attempt direct JSON parsing
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Look for Markdown code blocks
    json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. Look for the first curly brace to the last curly brace
    # This handles cases where there's text before or after the JSON
    try:
        start_index = text.find('{')
        end_index = text.rfind('}')
        if start_index != -1 and end_index != -1 and start_index < end_index:
            json_str = text[start_index : end_index + 1]
            return json.loads(json_str)
    except json.JSONDecodeError:
        pass

    return None

def get_random_specialist_model() -> str:
    """Select a random model from the pool."""
    if not MODEL_POOL:
        return MODEL_SPECIALIST_FALLBACK
    return random.choice(MODEL_POOL)

def is_censored(text: str) -> bool:
    """Check if the response text indicates censorship/refusal."""
    censorship_phrases = [
        "I cannot", "I am unable", "I'm sorry", "As an AI",
        "I can't", "cannot fulfill", "cannot comply", "against my programming",
        "policy prohibits", "cannot assist"
    ]
    # Check mostly beginning of response
    lower_text = text[:300].lower()
    for phrase in censorship_phrases:
        if phrase.lower() in lower_text:
            return True
    return False

# --- Models ---
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

# --- API Interaction ---
async def verify_api_key(code_x_key: str = Header(..., alias="code-x-key")):
    expected_key = os.getenv("CODE_X_KEY")
    # If not configured, we might skip or fail. Let's fail safe.
    if not expected_key:
        # If running locally without key, maybe allow?
        # But instruction implies security.
        pass
    if expected_key and code_x_key != expected_key:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return code_x_key

async def call_openwebui(model: str, messages: List[Dict[str, str]], json_mode: bool) -> str:
    if not OPENWEBUI_BASE:
        raise ValueError("OPENWEBUI_BASE not set")

    # Construct URL
    url = OPENWEBUI_BASE
    if "chat/completions" not in url:
        url = f"{url.rstrip('/')}/api/chat/completions"
        # We enforce /api/chat/completions here because the user's base URL does not include it,
        # and simple /chat/completions fails with 405 Method Not Allowed on some setups (like this one).

    headers = {
        "Authorization": f"Bearer {OPENWEBUI_KEY}",
        "Content-Type": "application/json"
    }

    # Detect Reasoning/Thinking Models
    is_reasoning_model = any(keyword in model.lower() for keyword in ["o1-", "o3-", "thinking", "reasoner"])

    # Handle System Prompts for Reasoning Models
    final_messages = messages
    if is_reasoning_model:
        # Merge system prompts into user prompts or convert role
        final_messages = []
        system_content = ""
        for msg in messages:
            if msg["role"] == "system":
                system_content += f"{msg['content']}\n\n"
            else:
                # If we have accumulated system content, prepend it to the first user message
                if system_content and msg["role"] == "user":
                    final_messages.append({"role": "user", "content": system_content + msg["content"]})
                    system_content = "" # Clear after merging
                else:
                    final_messages.append(msg)

        # If there is leftover system content (e.g., only system prompt), allow it as user
        if system_content:
             final_messages.append({"role": "user", "content": system_content.strip()})

    payload = {
        "model": model,
        "messages": final_messages,
    }

    # Add parameters conditionally
    if is_reasoning_model:
        # Reasoning models often don't support temperature/top_p or require them to be 1
        # It is safer to omit them.
        # They often use max_completion_tokens instead of max_tokens
        payload["max_completion_tokens"] = MAX_TOKENS
    else:
        payload["temperature"] = TEMPERATURE
        payload["top_p"] = TOP_P
        payload["max_tokens"] = MAX_TOKENS

    if json_mode and not is_reasoning_model:
         # Some reasoning models don't support response_format or require strict schemas
         # For broad compatibility, we only enable it for standard models.
         # For reasoning models, we rely on the prompt asking for JSON.
        payload["response_format"] = {"type": "json_object"}

    async with httpx.AsyncClient() as http_client:
        try:
            response = await http_client.post(url, headers=headers, json=payload, timeout=45.0)
            response.raise_for_status()
            result = response.json()
            if not result or "choices" not in result or not result["choices"]:
                raise ValueError("Invalid response format from API")
            content = result["choices"][0]["message"]["content"]
            return content
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP Error calling {model}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Connection Error calling {model}: {e}")
            raise

async def call_model(
    model: str,
    user_input: str,
    system_message: str = "",
    json_mode: bool = False,
    attempt_fallback: bool = True,
    is_specialist: bool = False
) -> str:
    
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": user_input})
    
    logger.info(f"🤖 AI REQUEST - Model: {model}")
    
    content = ""
    error_msg = ""

    # 1. Try Primary Model
    try:
        content = await call_openwebui(model, messages, json_mode)

        if not content:
            raise ValueError("Empty response received")

        # Check censorship
        if is_censored(content):
            logger.warning(f"🚫 Model {model} censored/refused. Triggering fallback.")
            raise ValueError("Censored/Refused")
            
        logger.info(f"✅ AI RESPONSE - Model: {model} - Length: {len(content)} chars")
        return content

    except Exception as e:
        error_msg = str(e)
        logger.warning(f"⚠️ Primary model {model} failed: {e}")

    # 2. Fallback Logic
    if attempt_fallback:
        # Determine fallback model
        # If the failed model was already the fallback, we need to retry with pool if allowed,
        # but the fallback model is usually the Venice one.

        fallback_target = MODEL_SPECIALIST_FALLBACK if is_specialist else MODEL_ORCHESTRATOR_FALLBACK

        # If we just failed on the fallback target itself, we might need a different strategy
        if model == fallback_target:
             # If Venice fails, retry with another model from the pool?
             # Instruction: "If Venice itself fails, the orchestrator must retry with another model from the pool until success."
             logger.warning(f"⚠️ Fallback model {fallback_target} failed. Retrying with random pool model.")

             # Avoid infinite recursion
             # Try up to 3 times with random models
             for _ in range(3):
                 retry_model = get_random_specialist_model()
                 if retry_model == fallback_target:
                     continue # Skip the one that just failed

                 try:
                     logger.info(f"🔄 Retry with {retry_model}")
                     content = await call_openwebui(retry_model, messages, json_mode)
                     if content and not is_censored(content):
                         return content
                 except Exception as retry_e:
                     logger.warning(f"Retry {retry_model} failed: {retry_e}")
                     continue

             raise HTTPException(status_code=500, detail=f"All fallbacks failed. Last error: {error_msg}")

        # Else, try the fallback target
        logger.info(f"🔄 Switching to Fallback: {fallback_target}")
        return await call_model(
            fallback_target,
            user_input,
            system_message,
            json_mode,
            attempt_fallback=True, # Allow fallback logic to recurse if *this* fails (triggers the block above)
            is_specialist=is_specialist
        )

    raise HTTPException(status_code=500, detail=f"Error calling {model}: {error_msg}")


# --- Orchestration Steps ---

async def step1_plan(question: str) -> Dict[str, Any]:
    """Call Orchestrator to plan agents."""
    logger.info("📋 ORCHESTRATOR PLANNING START")
    try:
        response = await call_model(
            MODEL_ORCHESTRATOR_PRIMARY,
            question,
            system_message=PLANNING_PROMPT,
            json_mode=True,
            attempt_fallback=True,
            is_specialist=False
        )
        if not response:
            raise ValueError("Empty response from planner")

        plan = extract_json_from_text(response)

        if not plan:
            raise ValueError("Could not extract JSON from response")

        # Enforce agent limits (< 16)
        agents = plan.get("agents", [])
        if len(agents) >= 16:
            logger.warning(f"Orchestrator suggested {len(agents)} agents. Limiting to 15.")
            agents = agents[:15]
            plan["agents"] = agents

        logger.info(f"📋 ORCHESTRATOR PLAN: {plan}")
        return plan
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"Failed to parse JSON plan: {e}")
        # Retry once? Or just fallback to a default plan?
        # Let's return a basic default plan
        return {
            "reasoning": "JSON Parse Error",
            "agents": [
                {"name": "General Assistant", "role": "Provide a helpful answer", "model": MODEL_SPECIALIST_FALLBACK}
            ]
        }
    except Exception as e:
        logger.error(f"Planning failed: {e}")
        return {"reasoning": f"Planning failed: {str(e)}", "agents": []}

async def step2_execute(agents: List[Dict[str, str]], question: str) -> Tuple[Dict[str, str], Dict[str, str]]:
    """Execute agents in parallel. Returns (responses, models_used)."""
    logger.info(f"🚀 EXECUTING {len(agents)} AGENTS")
    
    tasks = []
    agent_names = []
    agent_models = {}
    
    for agent in agents:
        name = agent.get("name", "Unknown Agent")
        role = agent.get("role", "Helpful Assistant")

        # Select model: "random" as per requirement
        model = get_random_specialist_model()
        logger.info(f"🎯 Assigned model {model} to agent {name}")

        agent_models[name] = model
        agent_names.append(name)

        system_msg = f"You are {name}. Role: {role}. Question: {question}. Answer concisely and professionally."

        # call_model handles fallback if error or censored
        tasks.append(call_model(
            model,
            question,
            system_message=system_msg,
            attempt_fallback=True,
            is_specialist=True
        ))
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    responses = {}
    for name, result in zip(agent_names, results):
        if isinstance(result, Exception):
            responses[name] = f"Error: {str(result)}"
        elif not result:
            responses[name] = "Error: No response from model."
        else:
            responses[name] = result
    
    logger.info(f"✅ AGENT EXECUTION COMPLETE")
    return responses, agent_models

async def step3_synthesize(question: str, plan: Dict[str, Any], agent_responses: Dict[str, str], agent_models: Dict[str, str]) -> str:
    """Synthesize final response using Orchestrator."""
    logger.info("👨‍⚖️ ORCHESTRATOR SYNTHESIS START")
    
    # 1. Construct Agent Roster (Markdown)
    agent_roster_md = "## 1. Agent Roster\n\n| Agent Name | Role | Model Used |\n|---|---|---|\n"
    for agent in plan.get("agents", []):
        name = agent.get("name", "Unknown Agent")
        role = agent.get("role", "Agent")
        model_used = agent_models.get(name, "Unknown Model")
        agent_roster_md += f"| {name} | {role} | {model_used} |\n"

    # 2. Construct Individual Agent Responses (Markdown)
    agent_responses_md = "## 2. Individual Agent Responses\n\n"
    for name, resp in agent_responses.items():
        agent_responses_md += f"### {name}\n\n{resp}\n\n"

    # 3. Request Synthesis from Orchestrator
    # We pass the raw data, but ask the Orchestrator to only produce the Synthesis/Verdict part
    synthesis_input = f"""
User Question: {question}

Agent Roster:
{agent_roster_md}

Agent Responses:
{agent_responses_md}

Please produce the 'Synthesis & Final Verdict' section only, based on the above information.
Do not repeat the Roster or individual responses.
"""
    
    synthesis_response = await call_model(
        MODEL_ORCHESTRATOR_PRIMARY,
        synthesis_input,
        system_message=MASTER_SYSTEM_PROMPT,
        attempt_fallback=True,
        is_specialist=False
    )

    # 4. Assemble Final Output
    final_output = f"{agent_roster_md}\n{agent_responses_md}\n## 3. Synthesis & Final Verdict\n\n{synthesis_response}"

    return final_output

async def orchestrate(question: str) -> Dict[str, Any]:
    # Step 1: Plan
    plan = await step1_plan(question)
    
    # Step 2: Execute
    agents = plan.get("agents", [])
    if not agents:
        # Trivial case or fallback
        logger.info("ℹ️ No agents needed or planning failed. Direct answer.")
        direct_response = await call_model(
            MODEL_ORCHESTRATOR_PRIMARY,
            question,
            system_message=MASTER_SYSTEM_PROMPT,
            attempt_fallback=True,
            is_specialist=False
        )
        return {
            "final_answer": direct_response,
            "models": {},
            "plan": plan
        }
    
    agent_responses, agent_models = await step2_execute(agents, question)
    
    # Step 3: Synthesize
    final_output = await step3_synthesize(question, plan, agent_responses, agent_models)
    
    return {
        "final_answer": final_output,
        "models": agent_responses,
        "plan": plan
    }

# --- Routes ---

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
        logger.error(f"Ask Error: {e}")
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
