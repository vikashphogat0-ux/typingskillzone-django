"""Printable passage sheets (Offscreen practice and paper tests).

Uses ReportLab, already in the project. Hindi needs a Devanagari font file, which is not yet
bundled, so Devanagari text is refused rather than printed as broken characters.
"""
import io
import re
from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

DEVANAGARI = re.compile(r"[\u0900-\u097F]")


class UnsupportedScript(ValueError):
    pass


def build_passage_pdf(*, test_number, exam_name, title, paragraphs):
    text = " ".join([title, exam_name, *paragraphs])
    if DEVANAGARI.search(text):
        raise UnsupportedScript("Hindi passage sheets need a Devanagari font, which is not installed yet.")
    buffer = io.BytesIO()
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    body.fontSize = 13
    body.leading = 20
    story = [
        Paragraph(escape(exam_name), styles["Heading4"]),
        Paragraph(escape(title), styles["Heading2"]),
        Paragraph(f"Test number: {escape(test_number)}", styles["Normal"]),
        Spacer(1, 8 * mm),
    ]
    for paragraph in paragraphs:
        story.append(Paragraph(escape(paragraph), body))
        story.append(Spacer(1, 4 * mm))

    def footer(canvas, document):
        canvas.saveState()
        canvas.setFont("Helvetica", 9)
        canvas.drawString(20 * mm, 10 * mm, f"TypingSkillZone · {test_number}")
        canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f"Page {document.page}")
        canvas.restoreState()

    document = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm, topMargin=20 * mm, bottomMargin=20 * mm, title=f"{test_number} {title}")
    document.build(story, onFirstPage=footer, onLaterPages=footer)
    return buffer.getvalue()
