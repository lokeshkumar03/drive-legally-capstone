import os
import re
from pathlib import Path
from typing import Dict, List

from dotenv import load_dotenv
from langchain.schema import Document
from langchain_community.document_loaders import PyPDFLoader
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter

from .file_utils import selected_doc_folders, state_folder_code

load_dotenv()

_VECTOR_CACHE: Dict[str, object] = {}
_EMBEDDING_INFO: Dict[str, str] = {"provider": "", "model": "", "status": ""}


def clean_legal_text(text: str) -> str:
    text = (text or "").replace("\n", " ")
    text = re.sub(r"\s+", " ", text).strip()
    # Normalize legal punctuation that looked odd in PDF output.
    text = text.replace(":—", ":").replace(".—", ".")
    text = text.replace(":-", ":").replace(" — ", " - ")
    return text


def _load_pdfs_for_state(state: str) -> List[Document]:
    documents: List[Document] = []
    folders = selected_doc_folders(state)
    for folder in folders:
        for pdf_path in Path(folder).glob("*.pdf"):
            try:
                loader = PyPDFLoader(str(pdf_path))
                docs = loader.load()
                for doc in docs:
                    doc.page_content = clean_legal_text(doc.page_content)
                    doc.metadata["source_file"] = pdf_path.name
                    # Keep this internally for retrieval, but do not display it in reports.
                    doc.metadata["state_db"] = Path(folder).name
                documents.extend(docs)
            except Exception as exc:
                documents.append(Document(page_content=f"Could not load {pdf_path.name}: {exc}", metadata={"source_file": pdf_path.name}))
    return documents


def _google_embeddings():
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    api_key = os.getenv("GOOGLE_API_KEY") or os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GOOGLE_API_KEY not configured")
    configured = os.getenv("GOOGLE_EMBEDDING_MODEL")
    candidates = []
    if configured:
        candidates.append(configured)
    # text-embedding-004 is widely supported by langchain-google-genai v2.x;
    # gemini-embedding-001 is the newer Gemini embedding model.
    candidates.extend(["models/text-embedding-004", "models/gemini-embedding-001", "gemini-embedding-001"] )
    seen = set()
    last_exc = None
    for model_name in [m for m in candidates if not (m in seen or seen.add(m))]:
        try:
            emb = GoogleGenerativeAIEmbeddings(model=model_name, google_api_key=api_key)
            # quick probe avoids failing later inside FAISS.from_documents
            emb.embed_query("test")
            _EMBEDDING_INFO.update({"provider": "GoogleGenerativeAIEmbeddings", "model": model_name, "status": "ok"})
            return emb
        except Exception as exc:
            last_exc = exc
    raise RuntimeError(f"No Google embedding model worked: {last_exc}")


def _get_embeddings():
    try:
        return _google_embeddings()
    except Exception as exc:
        # Offline fallback keeps app running, but retrieval quality is lower.
        from langchain_community.embeddings import FakeEmbeddings
        _EMBEDDING_INFO.update({"provider": "FakeEmbeddings", "model": "FakeEmbeddings-768", "status": f"fallback: {exc}"})
        return FakeEmbeddings(size=768)


def get_embedding_info() -> Dict[str, str]:
    return dict(_EMBEDDING_INFO)


def get_vector_store(state: str):
    code = state_folder_code(state) or "COMMON"
    embedding_model_key = os.getenv("GOOGLE_EMBEDDING_MODEL", "auto")
    cache_key = f"{code}:{embedding_model_key}"
    if cache_key in _VECTOR_CACHE:
        return _VECTOR_CACHE[cache_key]

    docs = _load_pdfs_for_state(code)
    if not docs:
        docs = [Document(page_content="No legal documents found for selected state.", metadata={"source_file": "none"})]

    splitter = RecursiveCharacterTextSplitter(chunk_size=2200, chunk_overlap=250)
    chunks = splitter.split_documents(docs)
    embeddings = _get_embeddings()
    vector_store = FAISS.from_documents(chunks, embeddings)
    _VECTOR_CACHE[cache_key] = vector_store
    return vector_store


def retrieve_legal_context(state: str, query: str, k: int = 5) -> List[Dict[str, str]]:
    vector_store = get_vector_store(state)
    docs = vector_store.similarity_search(query, k=k)
    results = []
    for doc in docs:
        page = doc.metadata.get("page", "")
        try:
            page = str(int(page) + 1) if str(page).isdigit() else str(page)
        except Exception:
            page = str(page)
        results.append({
            "section": doc.metadata.get("source_file", "Legal Document"),
            "state_db": doc.metadata.get("state_db", ""),  # internal only; UI/report hides it
            "page": page,
            "summary": clean_legal_text(doc.page_content)
        })
    return results
