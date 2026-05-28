import os
import re
import uuid
from pathlib import Path
from typing import Optional
from fastapi import UploadFile

BASE_DIR = Path(__file__).resolve().parent.parent
UPLOAD_DIR = BASE_DIR / "uploads"
REPORT_DIR = BASE_DIR / "reports"
LEGAL_DOCS_DIR = BASE_DIR / "legal_docs"

UPLOAD_DIR.mkdir(exist_ok=True)
REPORT_DIR.mkdir(exist_ok=True)


def safe_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_.-]", "_", filename or "uploaded_file")
    return cleaned[:150]


async def save_upload(file: Optional[UploadFile], prefix: str) -> str:
    if file is None:
        return ""
    ext = Path(file.filename).suffix or ".bin"
    name = f"{prefix}_{uuid.uuid4().hex}{ext}"
    path = UPLOAD_DIR / safe_filename(name)
    content = await file.read()
    path.write_bytes(content)
    return str(path)


def state_folder_code(state: str) -> str:
    normalized = (state or "").strip().upper()
    aliases = {
        "ANDHRA PRADESH": "AP",
        "AP": "AP",
        "TELANGANA": "TS",
        "TS": "TS",
        "KARNATAKA": "KA",
        "KA": "KA",
        "GUJARAT":"GJ",
        "GJ":"GJ"

    }
    return aliases.get(normalized, normalized)


def selected_doc_folders(state: str):
    code = state_folder_code(state)
    folders = [LEGAL_DOCS_DIR / "Common_db"]
    if code in {"AP", "TS", "KA","GJ"}:
        folders.append(LEGAL_DOCS_DIR / f"{code}_db")
    return [str(folder) for folder in folders if folder.exists()]
