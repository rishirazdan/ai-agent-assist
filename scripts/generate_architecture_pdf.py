from __future__ import annotations

from pathlib import Path

from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


ROOT = Path(__file__).resolve().parent.parent
INPUT_MD = ROOT / "ARCHITECTURE_AND_DECISIONS.md"
OUTPUT_PDF = ROOT / "ARCHITECTURE_AND_DECISIONS.pdf"


def build_pdf() -> None:
    text = INPUT_MD.read_text(encoding="utf-8")
    lines = [line.rstrip() for line in text.splitlines()]

    doc = SimpleDocTemplate(
        str(OUTPUT_PDF),
        pagesize=LETTER,
        leftMargin=0.8 * inch,
        rightMargin=0.8 * inch,
        topMargin=0.8 * inch,
        bottomMargin=0.8 * inch,
        title="AI Agent Assist - Architecture and Design Decisions",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("H1", parent=styles["Heading1"], fontSize=18, leading=22, spaceAfter=10)
    h2 = ParagraphStyle("H2", parent=styles["Heading2"], fontSize=13, leading=16, spaceBefore=8, spaceAfter=4)
    body = ParagraphStyle("Body", parent=styles["BodyText"], fontSize=10.5, leading=14)
    bullet = ParagraphStyle("Bullet", parent=styles["BodyText"], fontSize=10.5, leading=14, leftIndent=14)

    story = []
    for raw in lines:
        line = raw.strip()
        if not line:
            story.append(Spacer(1, 6))
            continue

        if line.startswith("# "):
            story.append(Paragraph(line[2:], h1))
            continue
        if line.startswith("## "):
            story.append(Paragraph(line[3:], h2))
            continue
        if line.startswith("- "):
            content = line[2:].replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(f"• {content}", bullet))
            continue
        if line[:2].isdigit() and line[1] == ".":
            content = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            story.append(Paragraph(content, body))
            continue

        content = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        story.append(Paragraph(content, body))

    doc.build(story)


if __name__ == "__main__":
    build_pdf()
