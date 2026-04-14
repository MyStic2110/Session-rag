import os
import uuid
import asyncio
import tempfile
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, cast, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, StreamingResponse
from pydantic import BaseModel
import httpx

load_dotenv(override=True)

SESSION_TIMEOUT_MINUTES = 15
CLEANUP_INTERVAL_SECONDS = 300
MAX_ACTIVE_ANALYSES = 5

# In-memory store refined for Health + Policy
SESSION_STORE: Dict[str, Any] = {}
WAITING_QUEUE: List[str] = []
ACTIVE_ANALYSES_COUNT = 0
QUEUE_LOCK = asyncio.Lock()

# Service Discovery Configuration
LLM_SERVICE_BASE_URL = os.environ.get("LLM_SERVICE_URL", "http://localhost:8001").rstrip("/")

app = FastAPI(title="LumeHealth - Medical AI & Insurance Intelligence")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
@app.middleware("http")
async def add_not_cache_header(request, call_next):
    response = await call_next(request)
    if "static" in request.url.path:
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    return response

app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")

@app.get("/")
async def root():
    return RedirectResponse(url="/static/index.html")

@app.on_event("startup")
async def startup_event():
    print("[INFO] LumeHealth Backend Starting...")
    asyncio.create_task(cleanup_sessions_job())

async def cleanup_sessions_job():
    while True:
        await asyncio.sleep(CLEANUP_INTERVAL_SECONDS)
        now = datetime.now()
        expired_sessions = []
        for session_id, data in SESSION_STORE.items():
            if now - data["last_accessed"] > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                expired_sessions.append(session_id)
        
        for session_id in expired_sessions:
            try:
                session_data = SESSION_STORE.get(session_id)
                if session_data and "mistral_file_ids" in session_data:
                    for f_id in session_data["mistral_file_ids"]:
                        try:
                            async with httpx.AsyncClient() as client:
                                await client.delete(f"{LLM_SERVICE_BASE_URL}/file/{f_id}")
                        except Exception:
                            pass
            except Exception:
                pass
            SESSION_STORE.pop(session_id, None)
            print(f"[CLEANUP] SESSION: {session_id} expired and destroyed.")

class SessionStartResponse(BaseModel):
    session_id: str

class AnalyzeRequest(BaseModel):
    session_id: str

class SessionEndRequest(BaseModel):
    session_id: str

@app.post("/session/start", response_model=SessionStartResponse)
async def start_session():
    session_id = str(uuid.uuid4())
    SESSION_STORE[session_id] = {
        "created_at": datetime.now(),
        "last_accessed": datetime.now(),
        "health_text": "",
        "policy_text": "",
        "mistral_file_ids": []
    }
    print(f"[INFO] NEW SESSION: {session_id}")
    return SessionStartResponse.model_construct(session_id=session_id)

@app.post("/session/end")
async def end_session(request: SessionEndRequest):
    session_id = request.session_id
    if session_id in SESSION_STORE:
        try:
            session_data = SESSION_STORE[session_id]
            for f_id in session_data["mistral_file_ids"]:
                try:
                    async with httpx.AsyncClient() as client:
                        await client.delete(f"{LLM_SERVICE_BASE_URL}/file/{f_id}")
                except Exception:
                    pass
        except Exception:
            pass
        SESSION_STORE.pop(session_id, None)
        print(f"[INFO] END SESSION: {session_id}")
        return {"status": "success", "message": "Session ended"}
    raise HTTPException(status_code=404, detail="Session not found")

def get_session(session_id: str) -> Dict[str, Any]:
    if session_id not in SESSION_STORE:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    session_data = cast(Dict[str, Any], SESSION_STORE[session_id])
    session_data["last_accessed"] = datetime.now()
    return session_data

@app.post("/upload")
async def upload_document(
    session_id: str = Form(...), 
    doc_type: str = Form(...), # 'health' or 'policy'
    file: UploadFile = File(...)
):
    print(f"[*] UPLOADING: {doc_type.upper()} file ({file.filename}) for session {session_id[:8]}...")
    session = get_session(session_id)
    
    raw_content = await file.read()
    content_bytes = cast(bytes, raw_content)
    
    if len(content_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")
    
    try:
        print(f"[*] MISTRAL OCR: Forwarding {file.filename} to LLM service...")
        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {'file': (file.filename, content_bytes, file.content_type)}
            data = {'doc_type': doc_type}
            resp = await client.post(f"{LLM_SERVICE_BASE_URL}/ocr", data=data, files=files)
            if resp.status_code != 200:
                raise Exception(resp.text)
            
            res_data = resp.json()
            full_text = res_data["text"]
            
        session["mistral_file_ids"].append(res_data["file_id"])
        
        if doc_type == "health":
            session["health_text"] = full_text
        else:
            session["policy_text"] = full_text
        
        print(f"[OK] OCR COMPLETE: {len(full_text)} chars extracted.")
            
    except Exception as e:
        print(f"[!] OCR ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")
            
    return {"status": "success", "type": doc_type}

@app.get("/queue/status/{session_id}")
async def get_queue_status(session_id: str):
    async with QUEUE_LOCK:
        if session_id in WAITING_QUEUE:
            pos = WAITING_QUEUE.index(session_id) + 1
            return {
                "status": "waiting",
                "position": pos,
                "total": len(WAITING_QUEUE),
                "wait_estimate": pos * 2 # 2 mins per person
            }
        return {"status": "ready"}

@app.post("/analyze")
async def analyze_health_insurance(request: AnalyzeRequest):
    global ACTIVE_ANALYSES_COUNT
    session_id = request.session_id
    print(f"[*] ANALYSIS REQUEST: Session {session_id[:8]}")
    
    session = get_session(session_id)
    
    async with QUEUE_LOCK:
        if ACTIVE_ANALYSES_COUNT >= MAX_ACTIVE_ANALYSES:
            if session_id not in WAITING_QUEUE:
                WAITING_QUEUE.append(session_id)
            pos = WAITING_QUEUE.index(session_id) + 1
            return {
                "status": "queued", 
                "position": pos, 
                "total": len(WAITING_QUEUE),
                "wait_estimate": pos * 2
            }
        
        # If was in queue, remove it
        if session_id in WAITING_QUEUE:
            WAITING_QUEUE.remove(session_id)
        
        ACTIVE_ANALYSES_COUNT += 1

    if not session["health_text"] or not session["policy_text"]:
        async with QUEUE_LOCK:
            ACTIVE_ANALYSES_COUNT -= 1
        raise HTTPException(status_code=400, detail="Both Health Report and Insurance Policy must be uploaded first.")

    try:
        print("[*] Forwarding to LLM microservice Layer 2 & 3...")
        async with httpx.AsyncClient(timeout=120.0) as client:
            payload = {
                "health_text": session['health_text'],
                "policy_text": session['policy_text']
            }
            resp = await client.post(f"{LLM_SERVICE_BASE_URL}/analyze", json=payload)
            if resp.status_code != 200:
                raise Exception(resp.text)
            
            analysis_data = resp.json()
            
        print("[OK] ANALYSIS COMPLETE: Intelligent Mapping finished.")
        return analysis_data
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"[!] ANALYSIS ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        async with QUEUE_LOCK:
            ACTIVE_ANALYSES_COUNT -= 1

@app.get("/analyze/stream/{session_id}")
async def analyze_health_insurance_stream(session_id: str):
    global ACTIVE_ANALYSES_COUNT
    print(f"[*] ANALYSIS STREAM REQUEST: Session {session_id[:8]}")
    
    session = get_session(session_id)
    
    if not session.get("health_text") or not session.get("policy_text"):
        raise HTTPException(status_code=400, detail="Both Health Report and Insurance Policy must be uploaded first.")
    
    async def event_generator():
        global ACTIVE_ANALYSES_COUNT
        
        while True:
            locked = False
            async with QUEUE_LOCK:
                if ACTIVE_ANALYSES_COUNT < MAX_ACTIVE_ANALYSES or (session_id in WAITING_QUEUE and WAITING_QUEUE[0] == session_id):
                    if session_id in WAITING_QUEUE:
                        WAITING_QUEUE.remove(session_id)
                    ACTIVE_ANALYSES_COUNT += 1
                    locked = True
                else:
                    if session_id not in WAITING_QUEUE:
                        WAITING_QUEUE.append(session_id)
                    pos = WAITING_QUEUE.index(session_id) + 1
                    total = len(WAITING_QUEUE)
                    
            if locked:
                break
            
            yield f"event: queue\ndata: {json.dumps({'position': pos, 'total': total, 'wait_estimate': pos * 2})}\n\n"
            await asyncio.sleep(5)
            
        try:
            print("[*] Forwarding to LLM microservice Stream...")
            payload = {
                "health_text": session['health_text'],
                "policy_text": session['policy_text']
            }
            async with httpx.AsyncClient(timeout=120.0) as client:
                async with client.stream("POST", f"{LLM_SERVICE_BASE_URL}/analyze/stream", json=payload) as response:
                    async for chunk in response.aiter_text():
                        yield chunk
        except Exception as e:
            print(f"[!] ANALYSIS STREAM ERROR: {str(e)}")
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"
        finally:
            async with QUEUE_LOCK:
                ACTIVE_ANALYSES_COUNT -= 1

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
