import sqlite3
import httpx
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import StreamingResponse
import json
import logging
import hashlib
import os
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("proxy_server")

app = FastAPI()

# Database setup
DB_NAME = os.getenv("DB_NAME", "proxy.db")
SALT = os.getenv("SALT")

if not SALT:
    logger.error("FATAL: SALT environment variable is not set!")
    raise RuntimeError("SALT environment variable is required for security.")

def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            device_id TEXT PRIMARY KEY,
            spent REAL DEFAULT 0.0
        )
    """)
    conn.commit()
    conn.close()

init_db()

OPENAI_API_URL = "https://api.openai.com/v1/chat/completions"
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")

BUDGET_LIMIT = 0.05

def verify_signature(device_id: str, signature: str) -> bool:
    expected = hashlib.sha256(f"{device_id}{SALT}".encode()).hexdigest()
    return expected == signature

def _sanitize_messages_for_openai(messages):
    """
    Attempts to fix the tool-calling structure to satisfy OpenAI's strict requirements.
    - Ensures every tool_call has a corresponding tool response.
    - Fixes mismatched or missing tool_call_ids.
    - Removes tool_calls that have no corresponding tool messages.
    """
    sanitized = []
    i = 0
    while i < len(messages):
        msg = messages[i].copy()
        role = msg.get("role")
        
        if role == "assistant" and msg.get("tool_calls"):
            tool_calls = msg["tool_calls"]
            valid_calls = []
            
            for tc in tool_calls:
                tc_id = tc.get("id")
                if not tc_id: continue
                
                found_response = False
                for j in range(i + 1, len(messages)):
                    next_msg = messages[j]
                    if next_msg.get("role") == "tool" and next_msg.get("tool_call_id") == tc_id:
                        found_response = True
                        break
                    if next_msg.get("role") != "tool": 
                        break
                
                if found_response:
                    valid_calls.append(tc)
            
            if valid_calls:
                msg["tool_calls"] = valid_calls
                if not msg.get("content"):
                    msg["content"] = None 
                sanitized.append(msg)
            else:
                if msg.get("content"):
                    del msg["tool_calls"]
                    sanitized.append(msg)
                else:
                    sanitized.append({"role": "assistant", "content": "[Thinking...]"})
        
        elif role == "tool":
            tc_id = msg.get("tool_call_id")
            has_call = False
            for s_msg in reversed(sanitized):
                if s_msg.get("role") == "assistant" and s_msg.get("tool_calls"):
                    if any(tc.get("id") == tc_id for tc in s_msg["tool_calls"]):
                        has_call = True
                        break
                if s_msg.get("role") != "assistant" and s_msg.get("role") != "tool":
                    break
            
            if has_call:
                sanitized.append(msg)
            else:
                content = msg.get("content", "")
                sanitized.append({"role": "user", "content": f"[Tool Output]: {content}"})
        else:
            sanitized.append(msg)
        
        i += 1
    return sanitized

@app.post("/v1/chat/completions")
async def proxy_chat(request: Request, x_signature: str = Header(None)):
    try:
        body = await request.json()
    except Exception as e:
        logger.error(f"Failed to parse JSON body: {e}")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    device_id = body.get("user", "unknown")
    
    # SECURITY CHECK
    if not x_signature:
        logger.warning(f"Request missing signature from {device_id}")
        raise HTTPException(status_code=403, detail="Signature missing")
    
    if not verify_signature(device_id, x_signature):
        logger.warning(f"Invalid signature from {device_id}. Signature: {x_signature}")
        raise HTTPException(status_code=403, detail="Invalid signature")

    logger.info(f"--- Authorized Request from: {device_id} ---")
    
    # 1. Check budget
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT spent FROM users WHERE device_id = ?", (device_id,))
    row = cursor.fetchone()
    
    if row is None:
        cursor.execute("INSERT INTO users (device_id, spent) VALUES (?, 0.0)", (device_id,))
        conn.commit()
        spent = 0.0
    else:
        spent = row[0]
    
    if spent >= BUDGET_LIMIT:
        conn.close()
        raise HTTPException(status_code=429, detail="Free trial limit reached ($0.05). Please provide your own API key in Settings.")

    # 2. OpenAI Request
    async def stream_generator():
        async with httpx.AsyncClient() as client:
            try:
                if not OPENAI_API_KEY:
                    logger.warning("OPENAI_API_KEY not set in environment!")
                    yield f"data: {json.dumps({'error': 'OPENAI_API_KEY not set on server'})}\n"
                    return

                oa_body = body.copy()
                oa_body["model"] = "gpt-4o-mini"
                
                if "messages" in oa_body:
                    oa_body["messages"] = _sanitize_messages_for_openai(oa_body["messages"])
                
                headers = {"Authorization": f"Bearer {OPENAI_API_KEY}"}
                
                async with client.stream("POST", OPENAI_API_URL, json=oa_body, headers=headers, timeout=60.0) as response:
                    if response.status_code == 200:
                        async for line in response.aiter_lines():
                            if not line: continue
                            yield f"{line}\n"
                            
                            if line.startswith("data: "):
                                data_str = line[6:]
                                if data_str == "[DONE]": continue
                                try:
                                    data = json.loads(data_str)
                                    usage = data.get("usage")
                                    if usage:
                                        # Cost for gpt-4o-mini: $0.15 / 1M input, $0.60 / 1M output
                                        cost = (usage['prompt_tokens'] * 0.00000015) + (usage['completion_tokens'] * 0.0000006)
                                        _update_spending(device_id, cost)
                                except: pass
                    elif response.status_code == 401:
                        logger.error("OpenAI API: 401 Unauthorized")
                        yield f"data: {json.dumps({'error': 'OpenAI API Unauthorized. Check server API key.'})}\n"
                    else:
                        error_detail = await response.aread()
                        logger.error(f"OpenAI API failed: {response.status_code} - {error_detail.decode()}")
                        yield f"data: {json.dumps({'error': f'OpenAI API Error: {response.status_code}'})}\n"
            except Exception as e:
                logger.error(f"OpenAI API connection failed: {e}")
                yield f"data: {json.dumps({'error': f'Server error: {str(e)}'})}\n"

    conn.close()
    return StreamingResponse(stream_generator(), media_type="text/event-stream")

def _update_spending(device_id, amount):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET spent = spent + ? WHERE device_id = ?", (amount, device_id))
    conn.commit()
    conn.close()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
