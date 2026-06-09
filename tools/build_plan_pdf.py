from __future__ import annotations

import re
import textwrap
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    Preformatted,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "docs" / "SynMax_Takehome_Architecture_Plan.md"
OUTPUT = ROOT / "docs" / "SynMax_Takehome_Architecture_Plan.pdf"


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#667085"))
    canvas.drawString(doc.leftMargin, 0.45 * inch, "SynMax Python Take-Home Architecture Plan")
    canvas.drawRightString(LETTER[0] - doc.rightMargin, 0.45 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _wrap_code(code: str, width: int = 92) -> str:
    wrapped_lines: list[str] = []
    for line in code.splitlines():
        if len(line) <= width:
            wrapped_lines.append(line)
            continue
        indent = re.match(r"^\s*", line).group(0)
        parts = textwrap.wrap(
            line,
            width=width,
            subsequent_indent=indent + "    ",
            break_long_words=True,
            break_on_hyphens=False,
        )
        wrapped_lines.extend(parts or [""])
    return "\n".join(wrapped_lines)


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "CustomTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=24,
            leading=30,
            textColor=colors.HexColor("#12343B"),
            alignment=TA_CENTER,
            spaceAfter=18,
        ),
        "h2": ParagraphStyle(
            "Heading2Custom",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=19,
            textColor=colors.HexColor("#14515C"),
            spaceBefore=16,
            spaceAfter=7,
        ),
        "h3": ParagraphStyle(
            "Heading3Custom",
            parent=base["Heading3"],
            fontName="Helvetica-Bold",
            fontSize=11.5,
            leading=15,
            textColor=colors.HexColor("#344054"),
            spaceBefore=12,
            spaceAfter=5,
        ),
        "body": ParagraphStyle(
            "BodyCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.4,
            leading=13.2,
            textColor=colors.HexColor("#1D2939"),
            spaceAfter=5,
        ),
        "bullet": ParagraphStyle(
            "BulletCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12.7,
            leftIndent=18,
            firstLineIndent=0,
            bulletIndent=7,
            textColor=colors.HexColor("#1D2939"),
            spaceAfter=3,
        ),
        "number": ParagraphStyle(
            "NumberCustom",
            parent=base["BodyText"],
            fontName="Helvetica",
            fontSize=9.2,
            leading=12.7,
            leftIndent=20,
            firstLineIndent=0,
            textColor=colors.HexColor("#1D2939"),
            spaceAfter=3,
        ),
        "code": ParagraphStyle(
            "CodeCustom",
            parent=base["Code"],
            fontName="Courier",
            fontSize=7.2,
            leading=9,
            textColor=colors.HexColor("#101828"),
        ),
    }


def _inline_markup(text: str) -> str:
    safe = escape(text)
    safe = re.sub(r"`([^`]+)`", r'<font name="Courier">\1</font>', safe)
    return safe


def build_story(markdown: str):
    styles = _styles()
    story = []
    in_code = False
    code_lines: list[str] = []

    for raw_line in markdown.splitlines():
        line = raw_line.rstrip()

        if line.startswith("```"):
            if in_code:
                code = _wrap_code("\n".join(code_lines))
                pre = Preformatted(escape(code), styles["code"])
                story.append(
                    Table(
                        [[pre]],
                        colWidths=[7.05 * inch],
                        style=TableStyle(
                            [
                                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#F2F4F7")),
                                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#D0D5DD")),
                                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                                ("TOPPADDING", (0, 0), (-1, -1), 6),
                                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                            ]
                        ),
                    )
                )
                story.append(Spacer(1, 6))
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue

        if in_code:
            code_lines.append(line)
            continue

        if not line.strip():
            story.append(Spacer(1, 3))
            continue

        if line == "---PAGE---":
            story.append(PageBreak())
            continue

        if line.startswith("# "):
            story.append(Spacer(1, 28))
            story.append(Paragraph(_inline_markup(line[2:].strip()), styles["title"]))
            story.append(Spacer(1, 8))
            continue

        if line.startswith("## "):
            story.append(Paragraph(_inline_markup(line[3:].strip()), styles["h2"]))
            continue

        if line.startswith("### "):
            story.append(Paragraph(_inline_markup(line[4:].strip()), styles["h3"]))
            continue

        if line.startswith("- "):
            story.append(Paragraph(_inline_markup(line[2:].strip()), styles["bullet"], bulletText="•"))
            continue

        numbered = re.match(r"^(\d+)\.\s+(.*)$", line)
        if numbered:
            story.append(
                Paragraph(
                    _inline_markup(numbered.group(2).strip()),
                    styles["number"],
                    bulletText=f"{numbered.group(1)}.",
                )
            )
            continue

        story.append(Paragraph(_inline_markup(line), styles["body"]))

    return story


def main() -> None:
    markdown = SOURCE.read_text(encoding="utf-8")
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=LETTER,
        rightMargin=0.72 * inch,
        leftMargin=0.72 * inch,
        topMargin=0.72 * inch,
        bottomMargin=0.72 * inch,
        title="SynMax Python Take-Home Architecture Plan",
        author="OpenAI Codex",
    )
    doc.build(build_story(markdown), onFirstPage=_footer, onLaterPages=_footer)
    print(OUTPUT)


if __name__ == "__main__":
    main()
