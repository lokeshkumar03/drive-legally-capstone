# Drive Legally

## AI Assistant for Traffic Challan Verification and Legal Guidance

Drive Legally is an Agentic AI-based LegalTech application that helps users verify traffic challans using OCR, AI Vision, state-wise legal document retrieval, legal compliance analysis, guardrails, and LLM-as-a-Judge evaluation.

The system allows users to upload a traffic challan image/PDF and vehicle evidence image, extract challan details, validate vehicle number, identify the latest offence, retrieve relevant legal provisions, compare fine amounts, and generate a structured PDF verification report.

---

## Project Overview

Digital traffic challans improve enforcement, but citizens may face difficulty verifying whether a challan is correct. Common issues include unclear evidence images, wrong vehicle numbers, incorrect offence details, wrong fine amounts, and lack of awareness of applicable traffic laws.

Drive Legally addresses this problem using a multi-agent AI workflow.

---

## Key Features

- Traffic challan image/PDF upload
- Vehicle front image upload
- Vehicle number extraction and matching
- Latest offence detection from multiple challan rows
- Fine amount, offence, date, time, location, and vehicle type extraction
- State-wise legal rule retrieval
- RAG-based legal reference search
- Legal question answering mode
- Fine validation against retrieved legal context
- Guardrails for hallucination reduction
- LLM-as-a-Judge evaluation
- Human/legal review escalation
- PDF report generation
- Premium React-based dashboard

---

## Supported User Types

- Vehicle Owner
- Legal Professional
- Traffic Officer
- Transport Department User
- Research / Academic User

---

## Technology Stack

### Frontend

- React
- Vite
- CSS / Modern dashboard styling

### Backend

- FastAPI
- Python
- LangGraph
- LangChain
- FAISS
- Google Gemini
- Gemini Vision
- Tesseract OCR
- OpenCV
- ReportLab
- LangSmith

---

## Agentic Workflow

The system uses multiple agents:

1. Evidence Analysis Agent  
   Extracts challan and vehicle evidence details using OCR and Gemini Vision.

2. Challan Validation Agent  
   Validates missing fields, vehicle number match, fine amount, image clarity, and multiple offence cases.

3. Router / Decision Agent  
   Decides whether the case should continue to legal analysis or be escalated for human review.

4. RAG Retrieval Agent  
   Retrieves relevant legal provisions from central and state-wise legal documents.

5. Legal Compliance Agent  
   Compares challan offence and fine amount with retrieved legal provisions.

6. Guardrails Agent  
   Checks answer safety, formatting, legal grounding, missing references, and unsupported claims.

7. LLM-as-a-Judge Agent  
   Evaluates the generated answer for grounding, citation support, state relevance, hallucination risk, clarity, and safety.

8. Human Review Escalation Agent  
   Flags uncertain or risky cases for manual review.

9. Report Agent  
   Generates the final structured PDF verification report.

---

## RAG and Legal Documents

The system uses Retrieval-Augmented Generation to retrieve applicable legal provisions.

Legal documents are stored under:

```text
backend/legal_docs/
Example structure:

backend/legal_docs/
├── Common_db/
│   ├── MVAct1988-59.pdf
│   ├── MVehicles_20(Amendment)Act_2019.pdf
│   └── RULES OF THE ROAD REGULATIONS, 1989.pdf
│
├── TS_db/
├── AP_db/
├── KA_db/
└── GJ_db/

Common DB contains central laws. State DB contains state-specific challan rules.

If a state-specific fine is available, the state rule is treated as final for fine comparison.

Project Architecture
React Frontend
     |
     v
FastAPI Backend
     |
     v
LangGraph Multi-Agent Workflow
     |
     |-- Evidence Analysis Agent
     |-- Validation Agent
     |-- RAG Retrieval Agent
     |-- Legal Compliance Agent
     |-- Guardrails Agent
     |-- LLM-as-a-Judge Agent
     |-- Report Agent
     |
     v
PDF Verification Report

Installation and Setup

1. Clone the Repository
git clone https://github.com/your-username/drive-legally-capstone.git
cd drive-legally-capstone

2. Go to Bakend Folder
cd backend

3. Create Virtual Environment
python -m venv venv

Activate it:

For Windows:

venv\Scripts\activate

For Mac/Linux:

source venv/bin/activate

4. Install Backend Dependencies
pip install -r requirements.txt

5. Create .env File

Copy .env.example to .env

For Windows:

copy .env.example .env

For Mac/Linux:

cp .env.example .env

Add your API key:

GOOGLE_API_KEY=your_google_gemini_api_key_here
GOOGLE_GENERATION_MODEL=gemini-2.5-flash
GOOGLE_VISION_MODEL=gemini-2.5-flash
GOOGLE_EMBEDDING_MODEL=models/text-embedding-004

LANGSMITH_TRACING=false
LANGSMITH_API_KEY=
LANGSMITH_PROJECT=Drive-Legally

TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe
6. Run Backend
uvicorn main:api --reload --host 0.0.0.0 --port 8000

Backend will run at:

http://localhost:8000


Frontend Setup

Open a new terminal.

7. Go to Frontend Folder
cd frontend
8. Install Frontend Dependencies
npm install
9. Run Frontend
npm run dev

Frontend will run at:

http://localhost:5173

Tesseract OCR Setup

For Windows, install Tesseract OCR and add the path in .env:

TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe

If Tesseract is not installed, the system can still use Gemini Vision fallback, but OCR accuracy may improve with Tesseract.

How to Use
Challan Verification Mode
Select user type.
Select state.
Enter name and vehicle number if available.
Upload challan image/PDF.
Upload vehicle front image.
Click Run AI Verification.
Review final status, legal analysis, issues, safety score, and PDF report.
Legal Question Mode
Select user type.
Select state.
Ask a traffic law question.
The system retrieves relevant legal provisions and generates an answer.

Example:

What is the fine for not wearing helmet in Telangana?
Output Report Includes
User and vehicle details
Latest challan offence
Vehicle validation result
Fine amount comparison
Evidence timestamp
Legal analysis
Legal references grouped by Act
Issues detected
Final verification status
Confidence score
Guardrails validation
LLM-as-a-Judge evaluation
Disclaimer
Responsible AI Features

Drive Legally includes:

RAG grounding
Guardrails validation
LLM-as-a-Judge evaluation
Confidence scoring
Human review escalation
Legal disclaimer

The system does not provide final legal advice. It provides assistive legal verification and awareness.

Limitations
OCR may fail on blurry or low-resolution images.
State-wise rules depend on the availability and quality of uploaded legal documents.
The system does not replace official traffic department verification.
Legal interpretation should be confirmed by a legal professional or authority.
Fine amounts may vary based on state notifications and updated rules.
Future Scope
Add more state-specific traffic rules.
Improve number plate detection using computer vision models.
Add multilingual support.
Add automatic challan portal integration.
Add user authentication and history.
Add dashboard analytics for traffic authorities.
Improve legal citation ranking and validation.
Add voice-based legal assistance.
Project Title

Drive Legally
AI Assistant for Traffic Challan Verification and Legal Guidance

Contributors
Chikkala Lokesh Kumar
