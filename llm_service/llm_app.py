import os
import tempfile
import json
from typing import Dict, Any, cast

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from mistralai.client import Mistral

load_dotenv(override=True)

app = FastAPI(title="LumeHealth - LLM Microservice")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

def get_mistral_client() -> Mistral:
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        print("[!] ERROR: Mistral API key not configured")
        raise HTTPException(status_code=500, detail="Mistral API key not configured")
    return Mistral(api_key=key)

class AnalyzePayload(BaseModel):
    health_text: str
    policy_text: str

@app.post("/ocr")
async def process_ocr(doc_type: str = Form(...), file: UploadFile = File(...)):
    print(f"[*] [LLM Service] Processing OCR for: {file.filename} of type {doc_type}")
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
        
        with open(tmp_path, "rb") as f:
            uploaded_file = client.files.upload(
                file={"file_name": file.filename, "content": f},
                purpose="ocr"
            )
        
        file_id = uploaded_file.id
        signed_url = client.files.get_signed_url(file_id=file_id)
        ocr_response = client.ocr.process(
            model="mistral-ocr-2512",
            document={"type": "document_url", "document_url": signed_url.url}
        )
        
        full_text = ""
        for page in ocr_response.pages:
            full_text += page.markdown + "\n\n"
        
        print(f"[OK] [LLM Service] OCR COMPLETE: {len(full_text)} chars extracted.")
        return {"status": "success", "text": full_text, "file_id": file_id}
            
    except Exception as e:
        print(f"[!] [LLM Service] OCR ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=f"OCR failed: {str(e)}")
    finally:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)

@app.delete("/file/{file_id}")
async def delete_file(file_id: str):
    try:
        client = get_mistral_client()
        client.files.delete(file_id=file_id)
        print(f"[*] [LLM Service] Deleted remote file {file_id}")
        return {"status": "success"}
    except Exception as e:
        print(f"[!] [LLM Service] Error deleting file {file_id}: {str(e)}")
        # We don't raise error to keep cleanup non-blocking
        return {"status": "error", "detail": str(e)}

@app.post("/analyze")
async def analyze_coverage(payload: AnalyzePayload):
    print(f"[*] [LLM Service] Starting Analysis...")
    client = get_mistral_client()
    
    try:
        extraction_prompt = f"""
        Extract deterministic data from the following health and insurance texts.
        Output ONLY valid JSON.
        
        HEALTH TEXT:
        {payload.health_text[:10000]}
        
        POLICY TEXT:
        {payload.policy_text[:10000]}
        
        JSON Structure:
        {{
            "health": {{
                "abnormal_parameters": ["string: parameter name only"],
                "domain_scores": {{ "cardio": 0-100, "liver": 0-100, "respiratory": 0-100, "metabolic": 0-100 }},
                "detected_patterns": ["string: identified trend"],
                "risk_projection": {{ "short": "string", "medium": "string", "long": "string" }},
                "overall_risk": "low|moderate|high"
            }},
            "insurance": {{
                "matched_policy_items": ["string: benefit name"],
                "coverage_details": {{ "covered": ["string"], "conditional": ["string"], "excluded": ["string"] }},
                "waiting_periods": ["string: period description"]
            }}
        }}
        STRICT RULES: 
        1. NO conversational text. 
        2. NO markdown formatting outside the JSON block.
        3. All numeric scores must be INTEGERS.
        4. Do NOT hallucinate data not present in texts.
        """
        extract_res = client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "user", "content": extraction_prompt}],
            response_format={"type": "json_object"}
        )
        deterministic_data = json.loads(extract_res.choices[0].message.content)

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
        INPUT DATA: {json.dumps(deterministic_data)}
        TASK: Generate the explanation following the 7 sections. 
        Section: "Future Coverage Mapping"
        For each map, use an "Intelligent Re-analysis" tone.
        Explain the mapping as: "Your insurance will cover this if you are within the policy period, otherwise you will pay from your pocket."
        Be specific about WHY (e.g. waiting periods, exclusions).
        STRICT SCHEME ENFORCEMENT:
        Every field below MUST be a STRING. Do NOT return sub-objects or arrays where a string is expected.
        STRICT SCHEME ENFORCEMENT:
        Every field below MUST be exactly as specified. 
        Strings must be meaningful explanations, not just "N/A" unless truly missing.
        REQUIRED OUTPUT JSON FORMAT:
        {{
            "summary": "1-2 paragraph executive summary",
            "abnormal_explanations": [{{ "parameter": "name", "explanation": "clear medical explanation" }}],
            "pattern_explanation": ["explanation of trend 1", "explanation of trend 2"],
            "risk_outlook": {{ 
                "short_term": "Optimistic|Stable|Concerning", 
                "medium_term": "Optimistic|Stable|Concerning", 
                "long_term": "Optimistic|Stable|Concerning", 
                "short_term_multiplier": "+0% to +100%", 
                "medium_term_multiplier": "+0% to +100%", 
                "long_term_multiplier": "+0% to +100%" 
            }},
            "recommendations": ["Actionable step 1", "Actionable step 2"],
            "insurance": {{ 
                "covered": ["Policy Item A", "Policy Item B"], 
                "conditional": ["Condition X", "Condition Y"], 
                "not_covered": ["Exclusion Z"], 
                "future_cost_awareness": "Detailed impact on future premiums/costs", 
                "potential_out_of_pocket_increase": "Percentage string" 
            }},
            "future_coverage_mapping": [{{ 
                "pattern": "Health Trend", 
                "future_condition": "Likely Diagnosis", 
                "coverage_status": "Covered|Excluded|Partial", 
                "coverage_gap_risk": "High|Medium|Low", 
                "severity_trend": "Increasing|Stable|Decreasing" 
            }}],
            "disclaimer": "Safety statement"
        }}
        """
        final_res = client.chat.complete(
            model="mistral-large-latest",
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": final_prompt}],
            response_format={"type": "json_object"}
        )
        analysis_data = json.loads(final_res.choices[0].message.content)
        print("[OK] [LLM Service] ANALYSIS COMPLETE.")
        return analysis_data
    except Exception as e:
        print(f"[!] [LLM Service] ANALYSIS ERROR: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/analyze/stream")
async def analyze_coverage_stream(payload: AnalyzePayload):
    print(f"[*] [LLM Service] Starting Analysis Stream...")
    client = get_mistral_client()
    
    async def event_generator():
        try:
            yield f"event: step\ndata: {json.dumps({'message': 'Extracting deterministic facts (Layer 2)', 'progress': 30})}\n\n"
            
            extraction_prompt = f"""
            Extract deterministic data from the following health and insurance texts.
            Output ONLY valid JSON.
            
            HEALTH TEXT:
            {payload.health_text[:10000]}
            
            POLICY TEXT:
            {payload.policy_text[:10000]}
            
            JSON Structure:
            {{
                "health": {{
                    "abnormal_parameters": ["string: parameter name only"],
                    "domain_scores": {{ "cardio": 0-100, "liver": 0-100, "respiratory": 0-100, "metabolic": 0-100 }},
                    "detected_patterns": ["string: identified trend"],
                    "risk_projection": {{ "short": "string", "medium": "string", "long": "string" }},
                    "overall_risk": "low|moderate|high"
                }},
                "insurance": {{
                    "matched_policy_items": ["string: benefit name"],
                    "coverage_details": {{ "covered": ["string"], "conditional": ["string"], "excluded": ["string"] }},
                    "waiting_periods": ["string: period description"]
                }}
            }}
            STRICT RULES: 
            1. NO conversational text. 
            2. NO markdown formatting outside the JSON block.
            3. All numeric scores must be INTEGERS.
            4. Do NOT hallucinate data not present in texts.
            """
            import asyncio
            def call_mistral():
                return client.chat.complete(
                    model="mistral-large-latest",
                    messages=[{"role": "user", "content": extraction_prompt}],
                    response_format={"type": "json_object"}
                )
            
            extract_res = await asyncio.to_thread(call_mistral)
            deterministic_data = json.loads(extract_res.choices[0].message.content)

            yield f"event: step\ndata: {json.dumps({'message': 'Formulating explanation parameters (Layer 3)', 'progress': 60})}\n\n"

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
            INPUT DATA: {json.dumps(deterministic_data)}
            TASK: Generate the explanation following the 7 sections. 
            Section: "Future Coverage Mapping"
            For each map, use an "Intelligent Re-analysis" tone.
            Explain the mapping as: "Your insurance will cover this if you are within the policy period, otherwise you will pay from your pocket."
            Be specific about WHY (e.g. waiting periods, exclusions).
            STRICT SCHEME ENFORCEMENT:
            Every field below MUST be a STRING. Do NOT return sub-objects or arrays where a string is expected.
            STRICT SCHEME ENFORCEMENT:
            Every field below MUST be exactly as specified. 
            Strings must be meaningful explanations, not just "N/A" unless truly missing.
            REQUIRED OUTPUT JSON FORMAT:
            {{
                "summary": "1-2 paragraph executive summary",
                "abnormal_explanations": [{{ "parameter": "name", "explanation": "clear medical explanation" }}],
                "pattern_explanation": ["explanation of trend 1", "explanation of trend 2"],
                "risk_outlook": {{ 
                    "short_term": "Optimistic|Stable|Concerning", 
                    "medium_term": "Optimistic|Stable|Concerning", 
                    "long_term": "Optimistic|Stable|Concerning", 
                    "short_term_multiplier": "+0% to +100%", 
                    "medium_term_multiplier": "+0% to +100%", 
                    "long_term_multiplier": "+0% to +100%" 
                }},
                "recommendations": ["Actionable step 1", "Actionable step 2"],
                "insurance": {{ 
                    "covered": ["Policy Item A", "Policy Item B"], 
                    "conditional": ["Condition X", "Condition Y"], 
                    "not_covered": ["Exclusion Z"], 
                    "future_cost_awareness": "Detailed impact on future premiums/costs", 
                    "potential_out_of_pocket_increase": "Percentage string" 
                }},
                "future_coverage_mapping": [{{ 
                    "pattern": "Health Trend", 
                    "future_condition": "Likely Diagnosis", 
                    "coverage_status": "Covered|Excluded|Partial", 
                    "coverage_gap_risk": "High|Medium|Low", 
                    "severity_trend": "Increasing|Stable|Decreasing" 
                }}],
                "disclaimer": "Safety statement"
            }}
            """
            
            def call_mistral_final():
                return client.chat.complete(
                    model="mistral-large-latest",
                    messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": final_prompt}],
                    response_format={"type": "json_object"}
                )
            
            final_res = await asyncio.to_thread(call_mistral_final)
            analysis_data = json.loads(final_res.choices[0].message.content)
            analysis_data["status"] = "success"
            
            yield f"event: result\ndata: {json.dumps(analysis_data)}\n\n"
            print("[OK] [LLM Service] ANALYSIS STREAM COMPLETE.")
            
        except Exception as e:
            print(f"[!] [LLM Service] ANALYSIS STREAM ERROR: {str(e)}")
            yield f"event: error\ndata: {json.dumps({'detail': str(e)})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("llm_app:app", host="0.0.0.0", port=port, reload=True)
