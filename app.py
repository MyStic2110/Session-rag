import os
import uuid
import asyncio
import tempfile
import json
from datetime import datetime, timedelta
from typing import Dict, List, Any, cast, Optional

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse, StreamingResponse, JSONResponse
from pydantic import BaseModel, validator
import httpx
import contextlib
from motor.motor_asyncio import AsyncIOMotorClient

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
_raw_url = os.environ.get("LLM_SERVICE_URL", "http://localhost:8001").rstrip("/")
if _raw_url and not _raw_url.startswith(("http://", "https://")):
    _raw_url = f"http://{_raw_url}"
LLM_SERVICE_BASE_URL = _raw_url

# --- Enterprise Shield: MongoDB Connectivity & Lifespan ---
db_client = None
db = None

@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    global db, db_client
    mongo_uri = os.environ.get("MONGO_URI")
    if mongo_uri:
        try:
            masked_uri = mongo_uri.split("@")[-1] if "@" in mongo_uri else "HIDDEN"
            print(f"[*] [Backend] Attempting MongoDB initialization (Host: {masked_uri})...")
            db_client = AsyncIOMotorClient(
                mongo_uri,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=10000,
                tlsAllowInvalidCertificates=True
            )
            # Connectivity check
            await db_client.admin.command('ping')
            db = db_client["lumehealth"]
            print(f"[OK] [Backend] MongoDB initialized successfully: {db.name}")
        except Exception as e:
            print(f"[!] [Backend] MongoDB Startup Connection Failed: {str(e)}")
            db = None
            db_client = None
    else:
        print("[!] [Backend] MONGO_URI not set. Database features disabled.")
    
    yield
    
    if db_client:
        db_client.close()

class AdvisorLead(BaseModel):
    name: str
    email: str
    phone: str
    agency: str
    experience: str
    specialization: str

    @validator('email')
    def validate_email(cls, v):
        import re
        v = v.strip()
        if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', v):
            raise ValueError('Please provide a valid email address.')
        return v

    @validator('name', 'agency', 'experience', 'specialization')
    def validate_non_empty(cls, v):
        if not v or not v.strip():
            raise ValueError('This field is required and cannot be empty.')
        return v.strip()

    @validator('phone')
    def validate_phone(cls, v):
        import re
        digits = re.sub(r'\D', '', v)
        if len(digits) < 7:
            raise ValueError('Please provide a valid phone number.')
        return v.strip()

app = FastAPI(title="LumeHealth - Medical AI & Insurance Intelligence", lifespan=lifespan)

# --- Global Exception Handlers: Always return clean JSON ---
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"[!!!] [Backend] Unhandled Exception on {request.url.path}: {str(exc)}")
    return JSONResponse(
        status_code=500,
        content={"detail": "Something went wrong on our end. Please try again."},
    )

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail},
    )

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

@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "service": "LumeHealth Main Backend",
        "sessions_active": len(SESSION_STORE),
        "llm_service": LLM_SERVICE_BASE_URL
    }

@app.on_event("startup")
async def startup_event():
    print(f"[INFO] LumeHealth Backend Starting...")
    print(f"[INFO] Target LLM Service: {LLM_SERVICE_BASE_URL}")
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

@app.post("/advisor/lead")
async def save_advisor_lead(lead: AdvisorLead):
    if not db:
        raise HTTPException(status_code=503, detail="Database connection unavailable")
    
    try:
        lead_data = lead.dict()
        lead_data["created_at"] = datetime.utcnow()
        lead_data["status"] = "new"
        
        await db.advisor_leads.insert_one(lead_data)
        return {"status": "success", "message": "Lead captured successfully"}
    except Exception as e:
        print(f"[!] Lead Capture Error: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to save lead information")

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
        "health_filename": "",
        "policy_filename": "",
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
        print(f"[!] SESSION NOT FOUND: {session_id}. Store size: {len(SESSION_STORE)}")
        raise HTTPException(status_code=404, detail="Session expired or backend restarted. Please refresh.")
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

    # Validate doc_type strictly
    if doc_type not in ("health", "policy"):
        raise HTTPException(status_code=400, detail="Invalid document type. Must be 'health' or 'policy'.")

    session = get_session(session_id)
    
    raw_content = await file.read()
    content_bytes = cast(bytes, raw_content)
    
    if len(content_bytes) > 5 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large. Maximum allowed size is 5MB. Please compress your document and try again.")

    # Server-side PDF magic byte check
    if not content_bytes.startswith(b'%PDF'):
        raise HTTPException(status_code=415, detail="Invalid file format. Please upload a valid PDF document.")

    if len(content_bytes) < 100:
        raise HTTPException(status_code=400, detail="The uploaded file appears to be empty or corrupted.")
    
    try:
        print(f"[*] MISTRAL OCR: Forwarding {file.filename} to LLM service...")
        async with httpx.AsyncClient(timeout=120.0) as client:
            files = {'file': (file.filename, content_bytes, file.content_type)}
            data = {'doc_type': doc_type}
            resp = await client.post(f"{LLM_SERVICE_BASE_URL}/ocr", data=data, files=files)
            if resp.status_code == 413:
                raise HTTPException(status_code=413, detail="File too large. Maximum allowed size is 5MB.")
            if resp.status_code == 415:
                raise HTTPException(status_code=415, detail="Invalid file format. Please upload a valid PDF.")
            if resp.status_code == 503:
                raise HTTPException(status_code=503, detail="Document scanner is temporarily unavailable. Please try again in a moment.")
            if resp.status_code != 200:
                err = resp.json().get('detail', resp.text) if resp.headers.get('content-type','').startswith('application/json') else resp.text
                raise HTTPException(status_code=resp.status_code, detail=f"Document processing failed: {err}")
            
            res_data = resp.json()
            full_text = res_data["text"]
            
        session["mistral_file_ids"].append(res_data["file_id"])
        
        if doc_type == "health":
            session["health_text"] = full_text
            session["health_filename"] = file.filename
        else:
            session["policy_text"] = full_text
            session["policy_filename"] = file.filename
        
        print(f"[OK] OCR COMPLETE: {len(full_text)} chars extracted.")
            
    except HTTPException:
        raise
    except httpx.TimeoutException:
        print(f"[!] OCR TIMEOUT: LLM service did not respond in time.")
        raise HTTPException(status_code=504, detail="Document processing timed out. The file may be too complex. Please try a smaller or simpler PDF.")
    except httpx.ConnectError:
        error_msg = f"Could not connect to Intelligence Engine at {LLM_SERVICE_BASE_URL}. It may be starting up."
        print(f"[!] CONNECTION ERROR: {error_msg}")
        raise HTTPException(status_code=503, detail="Intelligence Engine is starting up. Please wait a moment and try again.")
    except Exception as e:
        print(f"[!] OCR ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to process document. Please check the file is not password-protected and try again.")
            
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
        raise HTTPException(status_code=400, detail="Please upload both your medical report and insurance policy before running the analysis.")

    last_error = None
    for attempt in range(2):  # Retry once on transient failure
        try:
            print(f"[*] Forwarding to LLM microservice (attempt {attempt+1}/2)...")
            async with httpx.AsyncClient(timeout=120.0) as client:
                payload = {
                    "health_text": session['health_text'],
                    "policy_text": session['policy_text'],
                    "health_filename": session.get('health_filename'),
                    "policy_filename": session.get('policy_filename')
                }
                resp = await client.post(f"{LLM_SERVICE_BASE_URL}/analyze", json=payload)
                if resp.status_code != 200:
                    err = resp.json().get('detail', resp.text) if resp.headers.get('content-type','').startswith('application/json') else resp.text
                    raise Exception(err)
                
                analysis_data = resp.json()
                
            print("[OK] ANALYSIS COMPLETE: Intelligent Mapping finished.")
            return analysis_data
        
        except HTTPException:
            raise
        except httpx.TimeoutException:
            print(f"[!] ANALYSIS TIMEOUT on attempt {attempt+1}.")
            last_error = "Analysis timed out. The Intelligence Engine is under high load. Please try again in a moment."
            await asyncio.sleep(2)
            continue
        except httpx.ConnectError:
            print(f"[!] ANALYSIS CONNECTION ERROR on attempt {attempt+1}.")
            last_error = "Could not reach the Intelligence Engine. Please try again."
            break
        except Exception as e:
            print(f"[!] ANALYSIS ERROR: {str(e)}")
            last_error = str(e)
            break
        finally:
            if attempt == 1 or last_error is None:
                pass  # Decremented in outer finally

    raise HTTPException(status_code=503, detail=last_error or "Analysis failed. Please try again.")

@app.get("/analyze/stream/{session_id}")
async def analyze_health_insurance_stream(session_id: str):
    global ACTIVE_ANALYSES_COUNT
    print(f"[*] ANALYSIS STREAM REQUEST: Session {session_id[:8]}")
    
    session = get_session(session_id)
    
    if not session.get("health_text") or not session.get("policy_text"):
        raise HTTPException(status_code=400, detail="Please upload both your medical report and insurance policy before running the analysis.")
    
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
                "policy_text": session['policy_text'],
                "health_filename": session.get('health_filename'),
                "policy_filename": session.get('policy_filename')
            }
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream("POST", f"{LLM_SERVICE_BASE_URL}/analyze/stream", json=payload) as response:
                    if response.status_code == 422:
                        yield f"event: error\ndata: {json.dumps({'detail': 'The uploaded documents could not be processed. Please ensure they contain readable text.'})}\n\n"
                        return
                    if response.status_code >= 400:
                        yield f"event: error\ndata: {json.dumps({'detail': 'Intelligence Engine returned an error. Please try again.'})}\n\n"
                        return
                    async for chunk in response.aiter_text():
                        yield chunk
        except httpx.TimeoutException:
            print(f"[!] ANALYSIS STREAM TIMEOUT.")
            yield f"event: error\ndata: {json.dumps({'detail': 'Analysis timed out. The Intelligence Engine is under high load. Please try again in a moment.'})}\n\n"
        except httpx.ConnectError:
            print(f"[!] ANALYSIS STREAM CONNECT ERROR.")
            yield f"event: error\ndata: {json.dumps({'detail': 'Could not reach the Intelligence Engine. It may be starting up. Please try again.'})}\n\n"
        except Exception as e:
            print(f"[!] ANALYSIS STREAM ERROR: {str(e)}")
            yield f"event: error\ndata: {json.dumps({'detail': 'An unexpected error occurred during analysis. Please try again.'})}\n\n"
        finally:
            async with QUEUE_LOCK:
                ACTIVE_ANALYSES_COUNT -= 1

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("app:app", host="0.0.0.0", port=port, reload=True)
