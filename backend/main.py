import os
import uuid
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from models import ChallanState
from services.file_utils import save_upload, REPORT_DIR
from workflow.graph import build_verification_workflow, build_legal_question_workflow
from services.llm_service import gemini_status
from services.rag_service import get_embedding_info

load_dotenv()

# Optional LangSmith tracing for LangGraph workflow
if os.getenv("LANGSMITH_API_KEY"):
    os.environ.setdefault("LANGSMITH_TRACING", os.getenv("LANGSMITH_TRACING", "true"))
    os.environ.setdefault("LANGSMITH_PROJECT", os.getenv("LANGSMITH_PROJECT", "Drive-Legally-AI-Assistant"))

api = FastAPI(title="Drive Legally API", version="2.0.0")

api.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

verification_app = build_verification_workflow()
legal_question_app = build_legal_question_workflow()


def response_from_state(state: ChallanState):
    pdf_path = state.get("report_pdf_path", "")
    pdf_name = Path(pdf_path).name if pdf_path else ""
    return {
        **state,
        "report_pdf_url": f"/download-report/{pdf_name}" if pdf_name else "",
    }


@api.get("/health")
def health():
    return {"status": "ok", "message": "Drive Legally backend running"}




@api.get("/debug-config")
def debug_config():
    return {
        "gemini": gemini_status(),
        "embedding": get_embedding_info(),
        "langsmith_tracing": os.getenv("LANGSMITH_TRACING", "false"),
    }


@api.post("/verify-challan")
async def verify_challan(
    user_type: str = Form(...),
    selected_state: str = Form(...),
    user_name: str = Form(""),
    input_vehicle_number: str = Form(""),
    challan_file: UploadFile = File(...),
    vehicle_front_file: Optional[UploadFile] = File(None),
):
    request_id = uuid.uuid4().hex
    challan_path = await save_upload(challan_file, "challan")
    vehicle_path = await save_upload(vehicle_front_file, "vehicle_front") if vehicle_front_file else ""

    initial_state: ChallanState = {
        "request_id": request_id,
        "mode": "verify_challan",
        "user_type": user_type,
        "user_name": user_name,
        "input_vehicle_number": input_vehicle_number,
        "selected_state": selected_state,
        "challan_file_path": challan_path,
        "vehicle_front_file_path": vehicle_path,
        "challan_ocr_text": "",
        "vehicle_ocr_text": "",
        "vehicle_number": "",
        "vehicle_number_from_vehicle_image": "",
        "vehicle_match_status": "",
        "place_of_violation": "",
        "vehicle_type": "",
        "evidence_timestamp": "",
        "multiple_offences": False,
        "offence": "",
        "fine_amount": 0,
        "expected_fine": 0,
        "date_time": "",
        "ocr_confidence": 0,
        "image_quality": "",
        "validation_issues": [],
        "retrieved_sections": [],
        "legal_analysis": "",
        "confidence_score": 0,
        "final_status": "",
        "recommendation": [],
        "final_report": "",
        "report_pdf_path": "",
        "guardrail_result": {},
        "judge_result": {},
        "execution_log": ["Workflow started: Challan verification."],
    }
    final_state = verification_app.invoke(initial_state)
    return response_from_state(final_state)


@api.post("/ask-legal-question")
async def ask_legal_question(
    user_type: str = Form(...),
    selected_state: str = Form(...),
    question: str = Form(...),
    user_name: str = Form(""),
):
    request_id = uuid.uuid4().hex
    initial_state: ChallanState = {
        "request_id": request_id,
        "mode": "legal_question",
        "user_type": user_type,
        "user_name": user_name,
        "selected_state": selected_state,
        "legal_question": question,
        "validation_issues": [],
        "retrieved_sections": [],
        "legal_answer": "",
        "final_status": "",
        "confidence_score": 0,
        "final_report": "",
        "report_pdf_path": "",
        "guardrail_result": {},
        "judge_result": {},
        "execution_log": ["Workflow started: Legal fine/rule question."],
    }
    final_state = legal_question_app.invoke(initial_state)
    return response_from_state(final_state)


@api.get("/download-report/{filename}")
def download_report(filename: str):
    path = REPORT_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Report not found")
    return FileResponse(str(path), media_type="application/pdf", filename=filename)
