"""
pdf_report.py
-------------
Turns the agent's analysis text into a nicely formatted PDF.
The PDFs are saved in the "reports" folder and can be downloaded from the app.
"""

import os
import re
from datetime import datetime, timezone

from fpdf import FPDF

REPORTS_DIR = "reports"


def clean_text(text: str) -> str:
    """The built-in PDF fonts only know basic characters, so we tidy the text."""
    text = text.replace("**", "").replace("`", "").replace("\u2013", "-")
    text = text.replace("\u2014", "-").replace("\u2019", "'").replace("\u201c", '"')
    text = text.replace("\u201d", '"')
    # Replace anything the font can't draw (emojis etc.) with "?"
    return text.encode("latin-1", "replace").decode("latin-1")


class ReportPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 10)
        self.set_text_color(90, 90, 90)
        self.cell(0, 8, "Weather Analysis & Storm Prediction Report",
                  new_x="LMARGIN", new_y="NEXT")
        self.line(10, self.get_y(), 200, self.get_y())
        self.ln(4)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 10, f"Page {self.page_no()}  |  Data: WeatherAPI.com  |  "
                         "Forecast-based prediction, not an official warning",
                  align="C")


def create_pdf(city: str, title: str, body: str) -> str:
    """Build the PDF file and return its path."""
    os.makedirs(REPORTS_DIR, exist_ok=True)

    pdf = ReportPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # Title block
    pdf.set_text_color(20, 20, 20)
    pdf.set_font("Helvetica", "B", 18)
    pdf.multi_cell(0, 9, clean_text(title), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(90, 90, 90)
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    pdf.cell(0, 6, clean_text(f"City: {city}   |   Generated: {stamp}"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.ln(5)

    # Body: very small "markdown" reader (# headings, - bullets, normal text)
    pdf.set_text_color(30, 30, 30)
    for raw_line in body.splitlines():
        line = clean_text(raw_line.strip())
        pdf.set_x(10)
        if not line:
            pdf.ln(3)
        elif line.startswith("#"):
            pdf.ln(2)
            pdf.set_font("Helvetica", "B", 13)
            pdf.multi_cell(0, 7, line.lstrip("# ").strip(), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("Helvetica", "", 11)
        elif line.startswith(("- ", "* ")):
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, "  - " + line[2:], new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.set_font("Helvetica", "", 11)
            pdf.multi_cell(0, 6, line, new_x="LMARGIN", new_y="NEXT")

    safe_city = re.sub(r"[^a-z0-9]+", "-", city.lower()).strip("-") or "city"
    file_name = f"{safe_city}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    path = os.path.join(REPORTS_DIR, file_name)
    pdf.output(path)
    return path