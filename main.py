import os
import asyncio
import logging
import secrets
import time
import json
import random
import re
import httpx
import uuid
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple, Optional
from fastapi import FastAPI, HTTPException, Header, Depends, Form, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from starlette.middleware.sessions import SessionMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer
from system_prompts import MASTER_SYSTEM_PROMPT, PLANNING_PROMPT

# Async job processing imports
from database import (
    init_db, async_session_factory, create_async_job,
    get_job_by_slug, update_job_status, cleanup_expired_jobs,
    get_job_stats, JobStatus, AsyncJob
)
from job_processor import JobProcessor

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

# Follow-up Questions Feature Configuration
ENABLE_FOLLOWUP_QUESTIONS = os.getenv("ENABLE_FOLLOWUP_QUESTIONS", "true").lower() in ["true", "1", "yes"]
MAX_CONVERSATION_CONTEXT_LENGTH = int(os.getenv("MAX_CONVERSATION_CONTEXT_LENGTH", "8000"))  # chars
CONVERSATION_TIMEOUT_HOURS = int(os.getenv("CONVERSATION_TIMEOUT_HOURS", "24"))  # Auto-cleanup old conversations

# Async Job Processing Configuration (v1.2.0)
ENABLE_ASYNC_JOBS = os.getenv("ENABLE_ASYNC_JOBS", "true").lower() in ["true", "1", "yes"]
ASYNC_JOB_RETENTION_DAYS = int(os.getenv("ASYNC_JOB_RETENTION_DAYS", "30"))  # 30-day retention policy

# --- App Setup ---
app = FastAPI(title="Multi-Agent AI Orchestrator", version="1.2.0")

# --- Conversation Storage ---
# In-memory conversation storage (designed to be DB-compatible)
# Key: conversation_id (UUID), Value: Conversation dict
conversations_store: Dict[str, Dict[str, Any]] = {}

class ConversationMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str
    timestamp: datetime

class Conversation(BaseModel):
    id: str
    messages: List[ConversationMessage]
    verdict_content: Optional[str] = None  # Cached verdict for quick access
    created_at: datetime
    last_updated: datetime
    parent_conversation_id: Optional[str] = None  # For tracking continuation chains

# Global Exception Handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error(f"Global Exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal Server Error", "error": str(exc)},
    )

# Startup and Shutdown Events
@app.on_event("startup")
async def startup_event():
    """Initialize database and background tasks on startup"""
    if ENABLE_ASYNC_JOBS:
        logger.info("🚀 Initializing async job processing system...")
        await init_db()
        logger.info("✅ Database initialized successfully")

        # Start periodic cleanup task
        asyncio.create_task(periodic_cleanup_expired_jobs())
        logger.info("✅ Periodic cleanup task started")

async def periodic_cleanup_expired_jobs():
    """Background task to periodically clean up expired jobs"""
    while True:
        try:
            # Run cleanup every hour
            await asyncio.sleep(3600)

            async with async_session_factory() as session:
                deleted_count = await cleanup_expired_jobs(session)
                if deleted_count > 0:
                    logger.info(f"🗑️  Cleaned up {deleted_count} expired jobs")
        except Exception as e:
            logger.error(f"Error in periodic cleanup: {e}", exc_info=True)

# Security Headers Middleware
@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    return response

# Session Middleware (Required for CSRF)
# in production, ensure HTTPSOnly and SameSite settings are strict
app.add_middleware(SessionMiddleware, secret_key=os.getenv("CSRF_SECRET_KEY", secrets.token_hex(32)))

templates = Jinja2Templates(directory="templates")

# CSRF Protection
CSRF_SECRET_KEY = os.getenv("CSRF_SECRET_KEY", secrets.token_hex(32))
csrf_serializer = URLSafeTimedSerializer(CSRF_SECRET_KEY)

# --- Helpers ---
def generate_csrf_token(request: Request) -> str:
    """Generate a CSRF token and store it in the session."""
    token = secrets.token_urlsafe(32)
    request.session["csrf_token"] = token
    return token

def validate_csrf_token(request: Request, token: str) -> bool:
    """Validate a CSRF token against the session."""
    if not token:
        return False
    expected_token = request.session.get("csrf_token")
    if not expected_token:
        return False
    return secrets.compare_digest(token, expected_token)

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
    lower_text = text.lower()
    for phrase in censorship_phrases:
        if phrase.lower() in lower_text:
            return True
    return False

# --- Conversation Management Helpers ---

def generate_conversation_id() -> str:
    """Generate a unique conversation ID."""
    return str(uuid.uuid4())

def extract_verdict_from_response(response: str) -> Optional[str]:
    """
    Extract the '## 3. Synthesis & Final Verdict' section from the response.
    Returns the verdict content (including the heading) or None if not found.
    """
    # Look for the verdict section marker
    verdict_marker = "## 3. Synthesis & Final Verdict"

    if verdict_marker not in response:
        logger.warning("Verdict section not found in response")
        return None

    # Extract everything from the verdict marker onwards
    verdict_start = response.find(verdict_marker)
    verdict_content = response[verdict_start:].strip()

    return verdict_content

def create_conversation(question: str, response: str, parent_id: Optional[str] = None) -> str:
    """
    Create a new conversation and store it.
    Returns the conversation ID.
    """
    conv_id = generate_conversation_id()
    now = datetime.utcnow()

    # Extract verdict from response
    verdict = extract_verdict_from_response(response)

    conversation = {
        "id": conv_id,
        "messages": [
            {"role": "user", "content": question, "timestamp": now.isoformat()},
            {"role": "assistant", "content": response, "timestamp": now.isoformat()}
        ],
        "verdict_content": verdict,
        "created_at": now.isoformat(),
        "last_updated": now.isoformat(),
        "parent_conversation_id": parent_id
    }

    conversations_store[conv_id] = conversation
    logger.info(f"📝 Created conversation {conv_id} (parent: {parent_id})")

    return conv_id

def get_conversation(conversation_id: str) -> Optional[Dict[str, Any]]:
    """Retrieve a conversation by ID."""
    return conversations_store.get(conversation_id)

def add_message_to_conversation(conversation_id: str, role: str, content: str):
    """Add a message to an existing conversation."""
    conv = conversations_store.get(conversation_id)
    if not conv:
        logger.error(f"Conversation {conversation_id} not found")
        return

    now = datetime.utcnow()
    conv["messages"].append({
        "role": role,
        "content": content,
        "timestamp": now.isoformat()
    })
    conv["last_updated"] = now.isoformat()

    # Update verdict if this is an assistant message
    if role == "assistant":
        verdict = extract_verdict_from_response(content)
        if verdict:
            conv["verdict_content"] = verdict

def truncate_context(context: str, max_length: int = MAX_CONVERSATION_CONTEXT_LENGTH) -> str:
    """
    Truncate context to prevent excessive prompt growth.
    Keeps the most important parts and truncates from the middle if needed.
    """
    if len(context) <= max_length:
        return context

    logger.warning(f"Context truncated from {len(context)} to {max_length} chars")

    # Keep the beginning and end, truncate the middle
    keep_length = max_length // 2
    truncated = (
        context[:keep_length] +
        f"\n\n[... {len(context) - max_length} characters truncated for brevity ...]\n\n" +
        context[-keep_length:]
    )

    return truncated

def cleanup_old_conversations():
    """Remove conversations older than CONVERSATION_TIMEOUT_HOURS."""
    now = datetime.utcnow()
    to_remove = []

    for conv_id, conv in conversations_store.items():
        created_at = datetime.fromisoformat(conv["created_at"])
        age_hours = (now - created_at).total_seconds() / 3600

        if age_hours > CONVERSATION_TIMEOUT_HOURS:
            to_remove.append(conv_id)

    for conv_id in to_remove:
        del conversations_store[conv_id]
        logger.info(f"🧹 Cleaned up old conversation {conv_id}")

    if to_remove:
        logger.info(f"🧹 Cleaned up {len(to_remove)} old conversations")

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
    conversation_id: Optional[str] = None

class FollowUpRequest(BaseModel):
    question: str
    conversation_id: Optional[str] = None  # If provided, continue from this conversation

class FollowUpResponse(BaseModel):
    response: str
    conversation_id: str
    parent_conversation_id: Optional[str] = None

class AsyncJobSubmitResponse(BaseModel):
    """Response when submitting an async job"""
    url_slug: str
    result_url: str
    status: str
    created_at: str
    expires_at: str

class AsyncJobStatusResponse(BaseModel):
    """Response for job status/result queries"""
    url_slug: str
    question: str
    status: str
    response_content: Optional[str] = None
    error_message: Optional[str] = None
    conversation_id: Optional[str] = None
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    expires_at: str
    last_updated: str

# --- API Interaction ---
async def verify_api_key(code_x_key: str = Header(..., alias="code-x-key")):
    expected_key = os.getenv("CODE_X_KEY")
    # If not configured, we might skip or fail. Let's fail safe.
    if not expected_key:
        logger.error("CODE_X_KEY not configured. Refusing request.")
        raise HTTPException(status_code=500, detail="Server Misconfiguration: API Key not set")
    
    if code_x_key != expected_key:
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
            response = await http_client.post(url, headers=headers, json=payload, timeout=120.0)

            # Check for HTML content type explicitly
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                 raise ValueError(f"API returned HTML content (likely error page): {response.text[:200]}...")

            response.raise_for_status()

            try:
                result = response.json()
            except json.JSONDecodeError as e:
                # Issue 1: unexpected token '<' often means HTML response.
                if response.text.strip().startswith("<"):
                    raise ValueError(f"API returned HTML (likely error page) instead of JSON: {response.text[:200]}...")
                raise ValueError(f"Invalid JSON response: {str(e)}")

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
             # Issue 2: "In case fallback llm model also fail... auto use random llm model from llm model pool until success"
             logger.warning(f"⚠️ Fallback model {fallback_target} failed. Retrying with ALL available pool models until success.")

             # Get unique models from pool
             retry_candidates = list(dict.fromkeys(MODEL_POOL))
             # Shuffle to randomize order
             random.shuffle(retry_candidates)

             tried_models = set([model]) # Don't retry the one that just failed

             for retry_model in retry_candidates:
                 if retry_model in tried_models:
                     continue

                 try:
                     logger.info(f"🔄 Retry loop with {retry_model}")
                     content = await call_openwebui(retry_model, messages, json_mode)

                     if content and not is_censored(content):
                         logger.info(f"✅ Retry success with {retry_model}")
                         return content
                     elif is_censored(content):
                         logger.warning(f"🚫 Retry model {retry_model} was censored.")
                         tried_models.add(retry_model)
                 except Exception as retry_e:
                     logger.warning(f"Retry {retry_model} failed: {retry_e}")
                     tried_models.add(retry_model)
                     continue

             # If we exhausted the pool
             raise HTTPException(status_code=500, detail=f"All fallbacks and retry pool models failed. Last error: {error_msg}")

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

        # Enforce agent limits (< 10)
        agents = plan.get("agents", [])
        if len(agents) >= 10:
            logger.warning(f"Orchestrator suggested {len(agents)} agents. Limiting to 9.")
            agents = agents[:9]
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

        system_msg = f"You are {name}. Role: {role}. Answer concisely and professionally."

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

async def orchestrate(question: str, context: Optional[str] = None) -> Dict[str, Any]:
    """
    Orchestrate the multi-agent response.

    Args:
        question: The user's question
        context: Optional context from previous conversation (e.g., verdict content)

    Returns:
        Dict with final_answer, models, and plan
    """
    # If context is provided, prepend it to the question for all steps
    enhanced_question = question
    if context:
        context_truncated = truncate_context(context)
        enhanced_question = f"""Previous Context:
{context_truncated}

New Question: {question}

Please answer the new question taking into account the previous context."""
        logger.info(f"🔗 Using conversation context ({len(context_truncated)} chars)")

    # Step 1: Plan
    plan = await step1_plan(enhanced_question)

    # Step 2: Execute
    agents = plan.get("agents", [])
    if not agents:
        # Trivial case or fallback
        logger.info("ℹ️ No agents needed or planning failed. Direct answer.")
        direct_response = await call_model(
            MODEL_ORCHESTRATOR_PRIMARY,
            enhanced_question,
            system_message=MASTER_SYSTEM_PROMPT,
            attempt_fallback=True,
            is_specialist=False
        )
        return {
            "final_answer": direct_response,
            "models": {},
            "plan": plan
        }

    agent_responses, agent_models = await step2_execute(agents, enhanced_question)

    # Step 3: Synthesize
    final_output = await step3_synthesize(enhanced_question, plan, agent_responses, agent_models)

    return {
        "final_answer": final_output,
        "models": agent_responses,
        "plan": plan
    }

# --- Job Processor Initialization ---
# Initialize job processor for async background jobs
# We need to create a wrapper that returns the final answer and creates a conversation
async def orchestrate_for_job(question: str) -> Dict[str, Any]:
    """
    Wrapper for orchestrate that returns the final answer and conversation_id.
    Creates a conversation to enable follow-up questions for async jobs.

    Returns:
        Dict with 'response' (str) and 'conversation_id' (str)
    """
    result = await orchestrate(question)
    response = result["final_answer"]

    # Create a conversation to enable follow-up questions
    conversation_id = None
    if ENABLE_FOLLOWUP_QUESTIONS:
        conversation_id = create_conversation(question, response)
        logger.info(f"📝 Created conversation {conversation_id} for async job")

    return {
        "response": response,
        "conversation_id": conversation_id
    }

job_processor = JobProcessor(orchestrate_for_job)

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
        logger.error(f"Ask Error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    csrf_token = generate_csrf_token(request)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "csrf_token": csrf_token
    })

@app.get("/result/{url_slug}", response_class=HTMLResponse)
async def result_page(request: Request, url_slug: str):
    """
    Render the result page for an async job.
    This uses the same template as index but the JavaScript detects the URL pattern.
    """
    csrf_token = generate_csrf_token(request)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "csrf_token": csrf_token
    })

@app.post("/web-ask", response_model=WebResponse)
async def web_ask_question(
    request: Request,
    question: str = Form(...),
    csrf_token: str = Form(...)
):
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    try:
        # Cleanup old conversations periodically
        cleanup_old_conversations()

        result = await orchestrate(question)
        response_content = result["final_answer"]

        # Create conversation if follow-up feature is enabled
        conversation_id = None
        if ENABLE_FOLLOWUP_QUESTIONS:
            conversation_id = create_conversation(question, response_content)

        return WebResponse(
            response=response_content,
            conversation_id=conversation_id
        )
    except Exception as e:
        logger.error(f"Web error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.post("/web-followup", response_model=FollowUpResponse)
async def web_followup_question(
    request: Request,
    question: str = Form(...),
    conversation_id: str = Form(...),
    csrf_token: str = Form(...)
):
    """
    Handle follow-up questions by creating a new conversation seeded with
    the verdict from the previous conversation.
    """
    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    if not ENABLE_FOLLOWUP_QUESTIONS:
        raise HTTPException(status_code=400, detail="Follow-up questions feature is disabled")

    try:
        # Cleanup old conversations periodically
        cleanup_old_conversations()

        # Retrieve the parent conversation
        parent_conv = get_conversation(conversation_id)
        if not parent_conv:
            logger.warning(f"Parent conversation {conversation_id} not found, treating as new question")
            # Fall back to regular question handling
            result = await orchestrate(question)
            response_content = result["final_answer"]
            new_conv_id = create_conversation(question, response_content)
            return FollowUpResponse(
                response=response_content,
                conversation_id=new_conv_id,
                parent_conversation_id=None
            )

        # Extract verdict content for context
        verdict_context = parent_conv.get("verdict_content")
        if not verdict_context:
            logger.warning(f"No verdict found in conversation {conversation_id}, using last assistant message")
            # Fallback to using the last assistant message
            for msg in reversed(parent_conv["messages"]):
                if msg["role"] == "assistant":
                    verdict_context = msg["content"]
                    break

        # Orchestrate with context
        logger.info(f"🔄 Processing follow-up for conversation {conversation_id}")
        result = await orchestrate(question, context=verdict_context)
        response_content = result["final_answer"]

        # Create new conversation with parent link
        new_conv_id = create_conversation(question, response_content, parent_id=conversation_id)

        return FollowUpResponse(
            response=response_content,
            conversation_id=new_conv_id,
            parent_conversation_id=conversation_id
        )

    except Exception as e:
        logger.error(f"Follow-up error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal Server Error")

@app.get("/conversation/{conversation_id}")
async def get_conversation_history(conversation_id: str):
    """Retrieve a conversation's history."""
    if not ENABLE_FOLLOWUP_QUESTIONS:
        raise HTTPException(status_code=400, detail="Follow-up questions feature is disabled")

    conv = get_conversation(conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    return conv

# --- Async Job Endpoints (v1.2.0) ---

@app.post("/web-ask-async", response_model=AsyncJobSubmitResponse)
async def web_ask_question_async(
    request: Request,
    question: str = Form(...),
    csrf_token: str = Form(...)
):
    """
    Submit a question for async processing.
    Returns a unique URL immediately without waiting for completion.
    """
    if not ENABLE_ASYNC_JOBS:
        raise HTTPException(status_code=400, detail="Async job processing is disabled")

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    try:
        # Create async job in database
        async with async_session_factory() as session:
            job = await create_async_job(
                session,
                question=question,
                retention_days=ASYNC_JOB_RETENTION_DAYS
            )

            logger.info(f"📝 Created async job: id={job.id}, slug={job.url_slug}")

            # Start processing in background
            asyncio.create_task(job_processor.process_job(job.id, job.url_slug))

            # Return immediately with URL
            result_url = f"/result/{job.url_slug}"
            return AsyncJobSubmitResponse(
                url_slug=job.url_slug,
                result_url=result_url,
                status=job.status.value,
                created_at=job.created_at.isoformat(),
                expires_at=job.expires_at.isoformat()
            )

    except Exception as e:
        logger.error(f"Error creating async job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to create async job")


@app.get("/api/result/{url_slug}", response_model=AsyncJobStatusResponse)
async def get_job_result(url_slug: str):
    """
    API endpoint to get the status and result of an async job by its URL slug.
    Returns current status (queued/running/completed/failed) and result if available.
    """
    if not ENABLE_ASYNC_JOBS:
        raise HTTPException(status_code=400, detail="Async job processing is disabled")

    try:
        async with async_session_factory() as session:
            job = await get_job_by_slug(session, url_slug)

            if not job:
                raise HTTPException(status_code=404, detail="Job not found")

            # Check if expired
            if job.is_expired():
                # Return 410 Gone for expired jobs
                raise HTTPException(
                    status_code=410,
                    detail=f"This result has expired. Results are retained for {ASYNC_JOB_RETENTION_DAYS} days."
                )

            # Return job status and results
            return AsyncJobStatusResponse(
                url_slug=job.url_slug,
                question=job.question,
                status=job.status.value,
                response_content=job.response_content,
                error_message=job.error_message,
                conversation_id=job.conversation_id,
                created_at=job.created_at.isoformat(),
                started_at=job.started_at.isoformat() if job.started_at else None,
                completed_at=job.completed_at.isoformat() if job.completed_at else None,
                expires_at=job.expires_at.isoformat(),
                last_updated=job.last_updated.isoformat()
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrieving job result: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retrieve job result")


@app.post("/api/result/{url_slug}/retry")
async def retry_failed_job(
    request: Request,
    url_slug: str,
    csrf_token: str = Form(...)
):
    """
    API endpoint to retry a failed async job.
    Only works for jobs in FAILED status and not expired.
    """
    if not ENABLE_ASYNC_JOBS:
        raise HTTPException(status_code=400, detail="Async job processing is disabled")

    if not validate_csrf_token(request, csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")

    try:
        async with async_session_factory() as session:
            job = await get_job_by_slug(session, url_slug)

            if not job:
                raise HTTPException(status_code=404, detail="Job not found")

            if job.is_expired():
                raise HTTPException(
                    status_code=410,
                    detail=f"This job has expired. Jobs are retained for {ASYNC_JOB_RETENTION_DAYS} days."
                )

            if job.status != JobStatus.FAILED:
                raise HTTPException(
                    status_code=400,
                    detail=f"Can only retry failed jobs. Current status: {job.status.value}"
                )

            # Retry the job
            success = await job_processor.retry_job(job.id, url_slug)

            if success:
                return {"status": "retry_initiated", "url_slug": url_slug}
            else:
                raise HTTPException(status_code=500, detail="Failed to initiate retry")

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error retrying job: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to retry job")


@app.get("/admin/job-stats")
async def get_job_statistics():
    """
    Get statistics about async jobs (for monitoring).
    In production, this should be protected with authentication.
    """
    if not ENABLE_ASYNC_JOBS:
        raise HTTPException(status_code=400, detail="Async job processing is disabled")

    try:
        async with async_session_factory() as session:
            stats = await get_job_stats(session)
            return stats
    except Exception as e:
        logger.error(f"Error getting job stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to get job statistics")


@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "followup_enabled": ENABLE_FOLLOWUP_QUESTIONS,
        "async_jobs_enabled": ENABLE_ASYNC_JOBS
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=2000)
