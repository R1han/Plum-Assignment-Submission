"""Generate mock Indian medical documents for demo/UI testing.

Renders realistic prescriptions and bills (per sample_documents_guide.md)
as JPEGs into demo_documents/. The dates and patients align with
backend/data/policy_terms.json so uploads adjudicate correctly.

Usage:
    pip install pillow
    python scripts/generate_mock_documents.py
"""

from __future__ import annotations

import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

OUT = Path(__file__).resolve().parent.parent / "demo_documents"
W = 1000
MARGIN = 60

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf",          # macOS
    "/System/Library/Fonts/Helvetica.ttc",                   # macOS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",       # Linux
    "C:/Windows/Fonts/arial.ttf",                            # Windows
]
FONT_BOLD_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    for path in FONT_BOLD_CANDIDATES if bold else FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default(size)


class Doc:
    """Simple top-down document renderer."""

    def __init__(self, height: int = 1300):
        self.img = Image.new("RGB", (W, height), "#fdfcf8")
        self.d = ImageDraw.Draw(self.img)
        self.y = MARGIN
        # paper border
        self.d.rectangle([20, 20, W - 20, height - 20], outline="#888", width=2)

    def text(self, s: str, size: int = 26, bold: bool = False,
             color: str = "#1a1a1a", x: int = MARGIN, gap: int = 10):
        self.d.text((x, self.y), s, fill=color, font=_font(size, bold))
        self.y += size + gap

    def kv_row(self, left: str, right: str, size: int = 26):
        f = _font(size)
        self.d.text((MARGIN, self.y), left, fill="#1a1a1a", font=f)
        w = self.d.textlength(right, font=f)
        self.d.text((W - MARGIN - w, self.y), right, fill="#1a1a1a", font=f)
        self.y += size + 10

    def rule(self, gap: int = 18):
        self.y += 6
        self.d.line([MARGIN, self.y, W - MARGIN, self.y], fill="#999", width=2)
        self.y += gap

    def space(self, px: int = 14):
        self.y += px

    def table_row(self, cols: list[str], widths: list[float],
                  size: int = 25, bold: bool = False):
        f = _font(size, bold)
        x = MARGIN
        usable = W - 2 * MARGIN
        for col, frac in zip(cols, widths):
            if col.startswith("R:"):  # right-align numeric columns
                col = col[2:]
                w = self.d.textlength(col, font=f)
                self.d.text((x + usable * frac - w - 10, self.y), col,
                            fill="#1a1a1a", font=f)
            else:
                self.d.text((x, self.y), col, fill="#1a1a1a", font=f)
            x += usable * frac
        self.y += size + 12

    def signature(self, label: str):
        # squiggly signature line
        x0 = W - 380
        y0 = self.y + 28
        pts = []
        random.seed(7)
        for i in range(28):
            pts.append((x0 + i * 9, y0 + random.randint(-14, 14)))
        self.d.line(pts, fill="#1f3a93", width=3)
        self.d.text((x0, y0 + 26), label, fill="#444", font=_font(20))
        self.y = y0 + 60

    def stamp(self, lines: list[str], color: str = "#2e6da4"):
        cx, cy, r = W - 200, self.y + 10, 85
        self.d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=color, width=3)
        self.d.ellipse([cx - r + 8, cy - r + 8, cx + r - 8, cy + r - 8],
                       outline=color, width=2)
        fy = cy - len(lines) * 11
        for line in lines:
            f = _font(18, bold=True)
            w = self.d.textlength(line, font=f)
            self.d.text((cx - w / 2, fy), line, fill=color, font=f)
            fy += 24

    def save(self, name: str, blur: float = 0.0):
        img = self.img
        if blur:
            img = img.filter(ImageFilter.GaussianBlur(blur))
        OUT.mkdir(exist_ok=True)
        img.convert("RGB").save(OUT / name, "JPEG", quality=88)
        print(f"  {name}")


# ----------------------------------------------------------------------
def prescription(file_name: str, *, doctor: str, qual: str, reg: str,
                 clinic: str, addr: str, patient: str, age: str, date: str,
                 complaint: str, diagnosis: str, rx: list[str],
                 investigations: str | None = None, blur: float = 0.0):
    doc = Doc(1300)
    doc.text(doctor, 34, bold=True)
    doc.text(qual, 24, color="#444")
    doc.text(f"Reg. No: {reg}", 24, color="#444")
    doc.text(f"{clinic}, {addr}", 24, color="#444")
    doc.rule()
    doc.kv_row(f"Patient: {patient}", f"Date: {date}")
    doc.text(f"Age: {age}", 24)
    doc.text(f"Chief Complaint: {complaint}", 24)
    doc.rule()
    doc.text(f"Diagnosis: {diagnosis}", 28, bold=True)
    doc.space()
    doc.text("Rx:", 28, bold=True)
    for i, line in enumerate(rx, 1):
        doc.text(f"{i}. {line}", 26, x=MARGIN + 30)
    if investigations:
        doc.space()
        doc.text(f"Investigations: {investigations}", 24)
    doc.space(30)
    doc.signature(doctor)
    doc.stamp([clinic.split(",")[0].upper()[:14], "REGD."])
    doc.save(file_name, blur=blur)


def bill(file_name: str, *, facility: str, addr: str, gstin: str | None,
         bill_no: str, date: str, patient: str, age: str,
         ref_doctor: str | None, items: list[tuple[str, int, float]],
         blur: float = 0.0, title: str = "BILL / RECEIPT"):
    doc = Doc(1300)
    doc.text(facility.upper(), 34, bold=True)
    doc.text(addr, 24, color="#444")
    if gstin:
        doc.text(f"GSTIN: {gstin}", 24, color="#444")
    doc.rule()
    doc.text(title, 30, bold=True)
    doc.kv_row(f"Bill No: {bill_no}", f"Date: {date}")
    doc.rule()
    doc.text(f"Patient Name: {patient}", 26)
    doc.text(f"Age/Gender: {age}", 24)
    if ref_doctor:
        doc.text(f"Referring Doctor: {ref_doctor}", 24)
    doc.rule()
    doc.table_row(["DESCRIPTION", "R:QTY", "R:AMOUNT (Rs.)"],
                  [0.62, 0.16, 0.22], bold=True)
    total = 0.0
    for desc, qty, amount in items:
        doc.table_row([desc, f"R:{qty}", f"R:{amount:,.2f}"],
                      [0.62, 0.16, 0.22])
        total += amount
    doc.rule(10)
    doc.table_row(["", "R:Subtotal:", f"R:{total:,.2f}"], [0.5, 0.28, 0.22])
    doc.table_row(["", "R:GST (0% medical):", "R:0.00"], [0.5, 0.28, 0.22])
    doc.table_row(["", "R:Total Amount:", f"R:{total:,.2f}"],
                  [0.5, 0.28, 0.22], bold=True)
    doc.rule()
    doc.text("Payment Mode: UPI", 24)
    doc.signature("Authorised Signatory")
    doc.stamp([facility.split(",")[0].upper()[:14], "PAID"], color="#7a1f1f")
    doc.save(file_name, blur=blur)


def main():
    print(f"Writing to {OUT}/")

    # --- Scenario A: clean consultation approval (EMP001 Rajesh Kumar) ----
    prescription(
        "A1_prescription_rajesh.jpg",
        doctor="Dr. Arun Sharma", qual="MBBS, MD (Internal Medicine)",
        reg="KA/45678/2015", clinic="City Medical Centre",
        addr="12 MG Road, Bengaluru - 560001",
        patient="Rajesh Kumar", age="39 years / M", date="01-Nov-2024",
        complaint="Fever since 3 days, body ache",
        diagnosis="Viral Fever",
        rx=["Tab Paracetamol 650mg - 1-1-1 x 5 days",
            "Tab Vitamin C 500mg - 0-0-1 x 7 days"],
        investigations="CBC, Dengue NS1",
    )
    bill(
        "A2_hospital_bill_rajesh.jpg",
        facility="City Medical Centre",
        addr="12 MG Road, Bengaluru - 560001", gstin="29ABCDE1234F1ZX",
        bill_no="CMC/2024/08321", date="01-Nov-2024",
        patient="Rajesh Kumar", age="39 / Male", ref_doctor="Dr. Arun Sharma",
        items=[("Consultation Fee (OPD)", 1, 1000.00),
               ("CBC (Complete Blood Count)", 1, 300.00),
               ("Dengue NS1 Antigen Test", 1, 200.00)],
    )

    # --- Scenario B: wrong document (second prescription, no bill) --------
    prescription(
        "B1_prescription_rajesh_followup.jpg",
        doctor="Dr. Arun Sharma", qual="MBBS, MD (Internal Medicine)",
        reg="KA/45678/2015", clinic="City Medical Centre",
        addr="12 MG Road, Bengaluru - 560001",
        patient="Rajesh Kumar", age="39 years / M", date="06-Nov-2024",
        complaint="Follow-up visit, fever resolved",
        diagnosis="Viral Fever - resolved",
        rx=["Tab Vitamin C 500mg - 0-0-1 x 7 days (continue)"],
    )

    # --- Scenario C: unreadable pharmacy bill (EMP004 Sneha Reddy) --------
    prescription(
        "C1_prescription_sneha.jpg",
        doctor="Dr. Meena Pillai", qual="MBBS, MD",
        reg="KA/89012/2018", clinic="Jayanagar Family Clinic",
        addr="45 Jayanagar, Bengaluru - 560041",
        patient="Sneha Reddy", age="32 years / F", date="25-Oct-2024",
        complaint="Acidity, burning sensation",
        diagnosis="GERD",
        rx=["Cap Omeprazole 20mg - 1-0-0 x 14 days",
            "Syp Sucralfate - 1-1-1 x 10 days"],
    )
    bill(
        "C2_pharmacy_bill_sneha_BLURRY.jpg",
        facility="Health First Pharmacy",
        addr="22 Brigade Road, Bengaluru", gstin=None,
        bill_no="HFP-24-09821", date="25-Oct-2024",
        patient="Sneha Reddy", age="32 / Female", ref_doctor="Dr. Meena Pillai",
        items=[("Omeprazole 20mg x 14", 1, 320.00),
               ("Sucralfate Syrup 200ml", 2, 480.00)],
        title="PHARMACY BILL",
        blur=6.5,  # deliberately unreadable
    )

    # --- Scenario D: patient mismatch (bill for a different person) -------
    bill(
        "D1_hospital_bill_arjun_mehta.jpg",
        facility="City Medical Centre",
        addr="12 MG Road, Bengaluru - 560001", gstin="29ABCDE1234F1ZX",
        bill_no="CMC/2024/08355", date="01-Nov-2024",
        patient="Arjun Mehta", age="45 / Male", ref_doctor="Dr. Arun Sharma",
        items=[("Consultation Fee (OPD)", 1, 1000.00),
               ("X-Ray Chest PA View", 1, 500.00)],
    )

    # --- Scenario E: dental partial (EMP002 Priya Singh) -------------------
    bill(
        "E1_dental_bill_priya.jpg",
        facility="Smile Dental Clinic",
        addr="8 Koramangala 5th Block, Bengaluru", gstin=None,
        bill_no="SDC/2024/0455", date="15-Oct-2024",
        patient="Priya Singh", age="34 / Female", ref_doctor="Dr. N. Rao, BDS",
        items=[("Root Canal Treatment (Molar 36)", 1, 8000.00),
               ("Teeth Whitening (Cosmetic)", 1, 4000.00)],
        title="DENTAL TREATMENT INVOICE",
    )

    # --- Scenario F: network hospital discount (EMP010 Deepak Shah) -------
    prescription(
        "F1_prescription_deepak.jpg",
        doctor="Dr. S. Iyer", qual="MBBS, MD (Pulmonology)",
        reg="TN/56789/2013", clinic="Apollo Hospitals",
        addr="Greams Road, Chennai - 600006",
        patient="Deepak Shah", age="44 years / M", date="03-Nov-2024",
        complaint="Persistent cough, wheezing x 1 week",
        diagnosis="Acute Bronchitis",
        rx=["Tab Amoxicillin 500mg - 1-0-1 x 7 days",
            "Salbutamol Inhaler - 2 puffs SOS"],
    )
    bill(
        "F2_apollo_bill_deepak.jpg",
        facility="Apollo Hospitals",
        addr="Greams Road, Chennai - 600006", gstin="33APOLL1234H1Z2",
        bill_no="APH/OPD/2024/77123", date="03-Nov-2024",
        patient="Deepak Shah", age="44 / Male", ref_doctor="Dr. S. Iyer",
        items=[("Consultation Fee (Pulmonology OPD)", 1, 1500.00),
               ("Medicines (Pharmacy)", 1, 3000.00)],
    )

    print("Done.")


if __name__ == "__main__":
    main()
