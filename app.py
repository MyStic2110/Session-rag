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
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from mistralai.client import Mistral

load_dotenv(override=True)

SESSION_TIMEOUT_MINUTES = 30
CLEANUP_INTERVAL_SECONDS = 300

app = FastAPI(title="GhostPolicy - Health & Insurance Intelligence")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory store refined for Health + Policy
SESSION_STORE: Dict[str, Any] = {}

def get_mistral_client() -> Mistral:
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        print("[!] ERROR: Mistral API key not configured")
        raise HTTPException(status_code=500, detail="Mistral API key not configured")
    return Mistral(api_key=key)

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
    print("[INFO] GhostPolicy Backend Starting...")
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
                    client = get_mistral_client()
                    for f_id in session_data["mistral_file_ids"]:
                        try:
                            client.files.delete(file_id=f_id)
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
            client = get_mistral_client()
            session_data = SESSION_STORE[session_id]
            for f_id in session_data["mistral_file_ids"]:
                try:
                    client.files.delete(file_id=f_id)
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
    client = get_mistral_client()
    
    raw_content = await file.read()
    content_bytes = cast(bytes, raw_content)
    
    if len(content_bytes) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large. Maximum size is 10MB.")
    
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(content_bytes)
            tmp_path = tmp.name
        
        print(f"[*] MISTRAL OCR: Processing {file.filename}...")
        with open(tmp_path, "rb") as f:
            uploaded_file = client.files.upload(
                file={"file_name": file.filename, "content": f},
                purpose="ocr"
            )
        
        session["mistral_file_ids"].append(uploaded_file.id)
        
        signed_url = client.files.get_signed_url(file_id=uploaded_file.id)
        ocr_response = client.ocr.process(
            model="mistral-ocr-2512",
            document={"type": "document_url", "document_url": signed_url.url}
        )
        
        full_text = ""
        for page in ocr_response.pages:
            full_text += page.markdown + "\n\n"
            
        if doc_type == "health":
            session["health_text"] = full_text
        else:
            session["policy_text"] = full_text
        
        print(f"[OK] OCR COMPLETE: {len(full_text)} chars extracted.")
            
    except Exception as e:
        print(f"[!] OCR ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
            
    return {"status": "success", "type": doc_type}

@app.post("/analyze")
async def analyze_health_insurance(request: AnalyzeRequest):
    print(f"[*] ANALYSIS START: Session {request.session_id[:8]}")
    session = get_session(request.session_id)
    client = get_mistral_client()
    
    if not session["health_text"] or not session["policy_text"]:
        print("[!] ERROR: Missing document data for analysis.")
        raise HTTPException(status_code=400, detail="Both Health Report and Insurance Policy must be uploaded first.")
        
    try:
        # LAYER 2: Deterministic Extraction
        print("[*] LAYER 2: Extracting deterministic health/policy facts...")
        extraction_prompt = f"""
        Extract deterministic data from the following health and insurance texts.
        Output ONLY valid JSON.
        
        HEALTH TEXT:
        {session['health_text'][:10000]}
        
        POLICY TEXT:
        {session['policy_text'][:10000]}
        
        JSON Structure:
        {{
            "health": {{
                "abnormal_parameters": ["param1", "param2"],
                "domain_scores": {{ "cardio": 70, "liver": 40 }},
                "detected_patterns": ["pattern1"],
                "risk_projection": {{ "short": "", "medium": "", "long": "" }},
                "overall_risk": "moderate"
            }},
            "insurance": {{
                "matched_policy_items": [],
                "coverage_details": {{
                    "covered": [],
                    "conditional": [],
                    "excluded": []
                }},
                "waiting_periods": []
            }}
        }}
        """
        
        extract_res = client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": extraction_prompt}],
            response_format={"type": "json_object"}
        )
        
        deterministic_data = json.loads(extract_res.choices[0].message.content)
        print(f"[OK] LAYER 2 SUCCESS: {len(deterministic_data.get('health', {}).get('abnormal_parameters', []))} abnormalities found.")
        
        # LAYER 3: Explanation
        print("[*] LAYER 3: Generating final explanation and mapping...")
        system_prompt = """
        You are a health and insurance explanation assistant.
        You DO NOT perform any medical analysis, scoring, inference, or insurance eligibility decisions.
        All health analysis and insurance interpretations are provided to you as deterministic data.
        
        Your role is to:
        1. Explain the health data in simple terms
        2. Explain how health status relates to policy coverage
        3. Clearly present coverage strictly based on provided policy mapping
        
        STRICT RULES:
        - DO NOT calculate or override data.
        - DO NOT diagnose or predict specific diseases.
        - DO NOT give financial or medical advice.
        - Use CLEAR, CALM, and SUPPORTIVE tone.
        - Output STRICT JSON format as specified.
        
        SAFETY STATEMENT (MANDATORY):
        "This is not a medical diagnosis or insurance advice. Please consult a qualified healthcare professional and your insurance provider for detailed guidance."
        """
        
        final_prompt = f"""
        INPUT DATA:
        {json.dumps(deterministic_data)}
        
        TASK:
        Generate the explanation following the 7 sections. 
        
        Section: "Future Coverage Mapping"
        For each map, use an "Intelligent Re-analysis" tone.
        Explain the mapping as: "Your insurance will cover this if you are within the policy period, otherwise you will pay from your pocket."
        Be specific about WHY (e.g. waiting periods, exclusions).
        
        STRICT SCHEME ENFORCEMENT:
        Every field below MUST be a STRING. Do NOT return sub-objects or arrays where a string is expected.
        
        REQUIRED OUTPUT JSON FORMAT:
        {{
            "summary": "Full text string only",
            "abnormal_explanations": [{{ "parameter": "name", "explanation": "text string" }}],
            "pattern_explanation": ["string1", "string2"],
            "risk_outlook": {{ 
                "short_term": "string", "short_term_multiplier": "string (+XX%)",
                "medium_term": "string", "medium_term_multiplier": "string (+XX%)",
                "long_term": "string", "long_term_multiplier": "string (+XX%)"
            }},
            "recommendations": ["string1", "string2"],
            "insurance": {{
                "covered": ["string"],
                "conditional": ["string"],
                "not_covered": ["string"],
                "future_cost_awareness": "Full text string only",
                "potential_out_of_pocket_increase": "string (XX%)"
            }},
            "future_coverage_mapping": [
                {{ 
                    "pattern": "Technical pattern", 
                    "future_condition": "Future risk", 
                    "coverage_status": "EXPLANATION: 'Covered if within policy period vs Out-of-pocket' logic",
                    "coverage_gap_risk": "string (XX%)",
                    "severity_trend": "string (+XX%)"
                }}
            ],
            "disclaimer": "Safety statement"
        }}
        """
        
        final_res = client.chat.complete(
            model="mistral-large-latest",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": final_prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        analysis_data = json.loads(final_res.choices[0].message.content)
        print("[OK] ANALYSIS COMPLETE: Intelligent Mapping finished.")
        return analysis_data
        
    except Exception as e:
        print(f"[!] ANALYSIS ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
