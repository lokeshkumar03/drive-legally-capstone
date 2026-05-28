from pathlib import Path
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.units import inch
from reportlab.lib.enums import TA_CENTER

from .file_utils import REPORT_DIR


import re


def _escape(line: str) -> str:
    safe = (line or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("₹", "Rs.")
    # Convert simple markdown bold to ReportLab-supported inline bold tags.
    safe = re.sub(r"\*\*(.*?)\*\*", r"<b>\1</b>", safe)
    return safe


def create_pdf_report(request_id: str, markdown_report: str) -> str:
    pdf_path = REPORT_DIR / f"traffic_challan_report_{request_id}.pdf"
    doc = SimpleDocTemplate(str(pdf_path), pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle("TitleCustom", parent=styles["Title"], alignment=TA_CENTER, fontSize=16, spaceAfter=14)
    heading_style = ParagraphStyle("HeadingCustom", parent=styles["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=6)
    body_style = ParagraphStyle("BodyCustom", parent=styles["BodyText"], fontSize=9, leading=12, spaceAfter=3)

    story = []
    lines = markdown_report.splitlines()
    for raw in lines:
        line = raw.strip()
        if not line:
            story.append(Spacer(1, 0.08 * inch))
            continue
        safe = _escape(line)
        if safe.startswith("# "):
            story.append(Paragraph(safe[2:], title_style))
        elif safe.startswith("## "):
            story.append(Paragraph(safe[3:], heading_style))
        elif safe.startswith("- "):
            story.append(Paragraph("• " + safe[2:], body_style))
        else:
            story.append(Paragraph(safe, body_style))
    doc.build(story)
    return str(pdf_path)
