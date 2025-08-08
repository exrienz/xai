import os
import asyncio
import re
import logging
import secrets
import time
from typing import Dict, Any
from fastapi import FastAPI, HTTPException, Header, Depends, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pydantic import BaseModel
from cerebras.cloud.sdk import Cerebras
from dotenv import load_dotenv
from itsdangerous import URLSafeTimedSerializer

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()

app = FastAPI(title="Multi-Model AI Response Fusion", version="1.0.0")
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

async def call_cerebras_model(model: str, user_input: str, system_message: str = "") -> str:
    max_tokens = int(os.getenv("MAX_TOKENS", "1024"))
    temperature = float(os.getenv("TEMPERATURE", "0.7"))
    top_p = float(os.getenv("TOP_P", "0.8"))
    stream = os.getenv("STREAM", "false").lower() == "true"
    
    messages = []
    if system_message:
        messages.append({"role": "system", "content": system_message})
    messages.append({"role": "user", "content": user_input})
    
    # Log the request
    logger.info(f"🤖 AI REQUEST - Model: {model}")
    logger.info(f"📝 User Input: {user_input[:200]}{'...' if len(user_input) > 200 else ''}")
    if system_message:
        logger.info(f"🎯 System Message: {system_message[:100]}{'...' if len(system_message) > 100 else ''}")
    logger.info(f"⚙️ Parameters - Max Tokens: {max_tokens}, Temperature: {temperature}, Top-P: {top_p}, Stream: {stream}")
    
    try:
        if stream:
            # Handle streaming response
            logger.info(f"🌊 Starting streaming request to {model}")
            stream_response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stream=True
            )
            
            content = ""
            for chunk in stream_response:
                if chunk.choices[0].delta.content:
                    content += chunk.choices[0].delta.content
            
            # Log successful response
            logger.info(f"✅ AI RESPONSE - Model: {model} - Length: {len(content)} chars")
            logger.info(f"📤 Response Preview: {content[:300]}{'...' if len(content) > 300 else ''}")
            return content
        else:
            # Handle non-streaming response
            logger.info(f"⚡ Starting non-streaming request to {model}")
            chat_completion = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                top_p=top_p,
                stream=False
            )
            content = chat_completion.choices[0].message.content
            
            # Log successful response
            logger.info(f"✅ AI RESPONSE - Model: {model} - Length: {len(content)} chars")
            logger.info(f"📤 Response Preview: {content[:300]}{'...' if len(content) > 300 else ''}")
            return content
    except Exception as e:
        # Log the error
        logger.error(f"❌ AI REQUEST FAILED - Model: {model}")
        logger.error(f"🚨 Error: {str(e)}")
        logger.error(f"🔍 Error Type: {type(e).__name__}")
        raise HTTPException(status_code=500, detail=f"Error calling {model}: {str(e)}")

async def process_with_judge(user_input: str, model_responses: Dict[str, str]) -> Dict[str, str]:
    judge_model = os.getenv("JUDGE")
    if not judge_model:
        raise HTTPException(status_code=500, detail="Judge model not configured")
    
    # Log judge processing start
    logger.info(f"👨‍⚖️ JUDGE PROCESSING START")
    logger.info(f"📊 Model Response Lengths: MODEL1={len(model_responses.get('MODEL1', ''))}, MODEL2={len(model_responses.get('MODEL2', ''))}, MODEL3={len(model_responses.get('MODEL3', ''))}")
    
    judge_prompt = f"""You are an expert AI judge tasked with synthesizing responses from multiple AI models.

User Question: {user_input}

Model Responses:
MODEL1 ({os.getenv('MODEL1')}): {model_responses.get('MODEL1', 'No response')}

MODEL2 ({os.getenv('MODEL2')}): {model_responses.get('MODEL2', 'No response')}

MODEL3 ({os.getenv('MODEL3')}): {model_responses.get('MODEL3', 'No response')}

Please provide:
1. A final synthesized answer that combines the best aspects of all three responses
2. Your reasoning for how you arrived at this synthesis

IMPORTANT: Format your FINAL_ANSWER section using proper HTML markup:
- Use <h1>, <h2>, <h3> for headers
- Use <strong> for bold text instead of **bold**
- Use <em> for italic text instead of *italic*
- Use <ul><li> for bullet lists instead of - bullets
- Use <ol><li> for numbered lists instead of 1. 2. 3.
- Use <p> for paragraphs
- Use <hr> for horizontal rules instead of ---
- Use <blockquote> for quotes instead of >

Format your response as:
FINAL_ANSWER: [Your synthesized response in HTML format here]
REASONING: [Your reasoning process here]"""

    judge_response = await call_cerebras_model(judge_model, judge_prompt, "You are an expert AI judge that synthesizes multiple AI responses into a single, high-quality answer.")
    
    # Parse judge response
    logger.info(f"🔍 PARSING JUDGE RESPONSE - Length: {len(judge_response)} chars")
    logger.info(f"📄 Raw Judge Response (first 500 chars): {judge_response[:500]}")
    
    # Check if response contains expected markers
    has_final_answer = "FINAL_ANSWER:" in judge_response
    has_reasoning = "REASONING:" in judge_response
    logger.info(f"🏷️ Response markers found - FINAL_ANSWER: {has_final_answer}, REASONING: {has_reasoning}")
    
    lines = judge_response.split('\n')
    final_answer = ""
    reasoning = ""
    
    current_section = ""
    for i, line in enumerate(lines):
        if line.startswith("FINAL_ANSWER:"):
            current_section = "final_answer"
            final_answer = line.replace("FINAL_ANSWER:", "").strip()
            logger.info(f"🎯 Found FINAL_ANSWER at line {i}: {line[:100]}...")
        elif line.startswith("REASONING:"):
            current_section = "reasoning"
            reasoning = line.replace("REASONING:", "").strip()
            logger.info(f"🧠 Found REASONING at line {i}: {line[:100]}...")
        else:
            if current_section == "final_answer":
                final_answer += " " + line.strip()
            elif current_section == "reasoning":
                reasoning += " " + line.strip()
    
    # If parsing failed, try fallback approach
    if not final_answer.strip() and not reasoning.strip():
        logger.warning("⚠️ Standard parsing failed, trying fallback approach")
        
        # Try case-insensitive search
        response_upper = judge_response.upper()
        if "FINAL_ANSWER:" in response_upper or "FINAL ANSWER:" in response_upper:
            # Try to extract everything as final answer
            final_answer = judge_response.strip()
            logger.info("🔄 Using entire response as final_answer")
        else:
            # Last resort - use raw response
            final_answer = judge_response.strip()
            logger.warning("🚨 Using raw judge response as fallback")
    
    # Log judge processing result
    logger.info(f"✅ JUDGE PROCESSING COMPLETE")
    logger.info(f"📝 Final Answer Length: {len(final_answer.strip())} chars")
    logger.info(f"🧠 Reasoning Length: {len(reasoning.strip())} chars")
    logger.info(f"🎭 Final Answer Preview: {final_answer.strip()[:200]}{'...' if len(final_answer.strip()) > 200 else ''}")
    
    return {
        "final_answer": final_answer.strip(),
        "reasoning": reasoning.strip()
    }

def convert_to_markup(text: str) -> str:
    """Clean AI output for HTML display with comprehensive markdown support"""
    if not text:
        return ""
    
    # Step 1: Handle headers first (before bold processing to avoid conflicts)
    text = re.sub(r'^###\s*(.*)', r'<h3>\1</h3>', text, flags=re.MULTILINE)
    text = re.sub(r'^##\s*(.*)', r'<h2>\1</h2>', text, flags=re.MULTILINE)
    text = re.sub(r'^#\s*(.*)', r'<h1>\1</h1>', text, flags=re.MULTILINE)
    
    # Step 2: Handle horizontal rules
    text = re.sub(r'^---+', r'<hr>', text, flags=re.MULTILINE)
    
    # Step 3: Bold text: **text** -> <strong>text</strong>
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong>\1</strong>', text)
    
    # Step 4: Italic text: *text* -> <em>text</em>
    text = re.sub(r'\*(.*?)\*', r'<em>\1</em>', text)
    
    # Step 5: Process lines
    lines = text.split('\n')
    processed_lines = []
    
    for line in lines:
        line = line.strip()
        if not line:
            processed_lines.append('<br>')  # Empty lines become breaks
        elif line.startswith('<h') and line.endswith('>'):
            # Already processed header
            processed_lines.append(line)
        elif line.startswith('<hr>'):
            # Already processed horizontal rule
            processed_lines.append(line)
        elif line.startswith('- ') or re.match(r'^\d+\.\s', line):
            # Bullet points or numbered lists
            content = re.sub(r'^[-\d\.]+\s*', '', line)  # Remove bullet/number
            processed_lines.append(f'<li>{content}</li>')
        elif line.startswith('> '):
            # Blockquotes
            content = line[2:]  # Remove "> "
            processed_lines.append(f'<blockquote class="blockquote"><p>{content}</p></blockquote>')
        else:
            # Regular text line
            processed_lines.append(f'<p>{line}</p>')
    
    # Join lines
    text = '\n'.join(processed_lines)
    
    # Step 6: Group consecutive list items
    text = re.sub(r'(<li>.*?</li>\n?)+', lambda m: f'<ul class="list-unstyled">\n{m.group(0)}</ul>', text, flags=re.DOTALL)
    
    # Step 7: Clean up
    text = re.sub(r'<p></p>', '', text)
    text = re.sub(r'<br>\s*<br>', '<br>', text)  # Remove duplicate breaks
    text = re.sub(r'\n+', '\n', text)
    
    return text.strip()

@app.post("/ask", response_model=ModelResponse)
async def ask_question(
    request: QuestionRequest,
    api_key: str = Depends(verify_api_key)
):
    model1 = os.getenv("MODEL1")
    model2 = os.getenv("MODEL2")
    model3 = os.getenv("MODEL3")
    
    if not all([model1, model2, model3]):
        raise HTTPException(status_code=500, detail="Models not properly configured")
    
    # Call all three models concurrently
    tasks = [
        call_cerebras_model(model1, request.question, request.system_message),
        call_cerebras_model(model2, request.question, request.system_message),
        call_cerebras_model(model3, request.question, request.system_message)
    ]
    
    try:
        responses = await asyncio.gather(*tasks)
        
        model_responses = {
            "MODEL1": responses[0],
            "MODEL2": responses[1],
            "MODEL3": responses[2]
        }
        
        # Process with judge
        judge_result = await process_with_judge(request.question, model_responses)
        
        # Check if we should show model outputs
        show_model_output = os.getenv("SHOW_MODEL_OUTPUT", "false").lower() == "true"
        
        return ModelResponse(
            input=request.question,
            models=model_responses if show_model_output else None,
            judge=judge_result
        )
    
    except HTTPException as he:
        # Re-raise HTTPExceptions from underlying functions
        raise he
    except Exception as e:
        error_msg = str(e) if str(e) else f"Unknown error of type {type(e).__name__}"
        raise HTTPException(status_code=500, detail=f"Error processing request: {error_msg}")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    csrf_token = generate_csrf_token()
    logger.info(f"🔐 Generated CSRF token for new session: {csrf_token[:20]}...")
    return templates.TemplateResponse("index.html", {
        "request": request,
        "csrf_token": csrf_token
    })

@app.post("/web-ask", response_model=WebResponse)
async def web_ask_question(
    question: str = Form(...),
    csrf_token: str = Form(...)
):
    """Secure backend endpoint for web interface"""
    # Log request start
    logger.info(f"🌐 WEB REQUEST START")
    logger.info(f"❓ Question: {question[:100]}{'...' if len(question) > 100 else ''}")
    logger.info(f"📏 Question Length: {len(question)} chars")
    logger.info(f"🔐 CSRF Token received: {csrf_token[:20]}...")
    
    # Validate CSRF token
    if not validate_csrf_token(csrf_token):
        logger.warning(f"🚨 INVALID CSRF TOKEN - Potential scraping attempt blocked")
        raise HTTPException(status_code=403, detail="Invalid or expired CSRF token")
    
    logger.info(f"✅ CSRF token validated successfully")
    
    try:
        # Get models from environment
        model1 = os.getenv("MODEL1")
        model2 = os.getenv("MODEL2") 
        model3 = os.getenv("MODEL3")
        
        logger.info(f"🧠 Using Models: {model1}, {model2}, {model3}")
        
        if not all([model1, model2, model3]):
            logger.error("❌ Models not properly configured")
            raise HTTPException(status_code=500, detail="Models not properly configured")
        
        # Call all three models concurrently
        logger.info(f"🚀 Starting concurrent model calls")
        tasks = [
            call_cerebras_model(model1, question),
            call_cerebras_model(model2, question),
            call_cerebras_model(model3, question)
        ]
        
        responses = await asyncio.gather(*tasks)
        logger.info(f"✅ All model responses received")
        
        model_responses = {
            "MODEL1": responses[0],
            "MODEL2": responses[1], 
            "MODEL3": responses[2]
        }
        
        # Process with judge
        judge_result = await process_with_judge(question, model_responses)
        
        # Judge now provides HTML directly, so use it as-is
        final_response = judge_result["final_answer"]
        
        # Log successful completion
        logger.info(f"🎉 WEB REQUEST COMPLETE")
        logger.info(f"📤 Final Response Length: {len(final_response)} chars")
        logger.info(f"🏁 Response Preview: {final_response[:150]}{'...' if len(final_response) > 150 else ''}")
        
        return WebResponse(response=final_response)
        
    except HTTPException as he:
        # Log HTTP exceptions (these are expected errors)
        logger.warning(f"⚠️ HTTP Exception: {he.detail}")
        raise he
    except Exception as e:
        # Log unexpected errors
        error_msg = str(e) if str(e) else f"Unknown error of type {type(e).__name__}"
        logger.error(f"💥 UNEXPECTED ERROR in web_ask_question")
        logger.error(f"🚨 Error: {error_msg}")
        logger.error(f"🔍 Error Type: {type(e).__name__}")
        raise HTTPException(status_code=500, detail=f"Error processing request: {error_msg}")

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=2000)
