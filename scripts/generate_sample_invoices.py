"""
Generate the bundled sample PDF invoices.

Run once to regenerate sample_pdfs/. Each invoice is a realistic SMB bill,
with three intentional anomalies seeded so the extraction pipeline has
something to catch:

  - SUPPLY-2025-007 (Misc Supplier):  math error — line items don't reconcile
  - NOT-2025-1042 (Notion, 2 PDFs):   duplicate invoice number from same vendor
  - INV-90217 (Linode):               missing due date

Outputs go to ../sample_pdfs/.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
)


OUTPUT_DIR = Path(__file__).parent.parent / "sample_pdfs"


@dataclass
class LineItem:
    description: str
    qty: float
    unit_price: float

    @property
    def total(self) -> float:
        return round(self.qty * self.unit_price, 2)


@dataclass
class Invoice:
    filename: str
    vendor_name: str
    vendor_address: str
    bill_to: str
    invoice_number: str
    invoice_date: str
    due_date: Optional[str]
    line_items: list[LineItem]
    tax_rate: float = 0.0
    # Override the printed subtotal/tax/total to seed a math anomaly.
    printed_subtotal: Optional[float] = None
    printed_tax: Optional[float] = None
    printed_total: Optional[float] = None
    notes: str = ""

    @property
    def subtotal(self) -> float:
        return round(sum(li.total for li in self.line_items), 2)

    @property
    def tax(self) -> float:
        return round(self.subtotal * self.tax_rate, 2)

    @property
    def total(self) -> float:
        return round(self.subtotal + self.tax, 2)


def render_invoice(inv: Invoice, path: Path) -> None:
    doc = SimpleDocTemplate(
        str(path),
        pagesize=LETTER,
        leftMargin=0.6 * inch,
        rightMargin=0.6 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title=f"Invoice {inv.invoice_number}",
    )

    styles = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=22, spaceAfter=4)
    small = ParagraphStyle("small", parent=styles["Normal"], fontSize=9, leading=11)
    normal = styles["Normal"]
    right = ParagraphStyle("right", parent=normal, alignment=2)

    story = []

    # Header
    header = [
        [
            Paragraph(f"<b>{inv.vendor_name}</b><br/>"
                      f"<font size=9>{inv.vendor_address}</font>", normal),
            Paragraph("<b>INVOICE</b>", h1),
        ]
    ]
    t = Table(header, colWidths=[3.5 * inch, 3.5 * inch])
    t.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (1, 0), (1, 0), "RIGHT"),
    ]))
    story.append(t)
    story.append(Spacer(1, 0.25 * inch))

    # Metadata
    meta_rows = [
        ["Invoice #:", inv.invoice_number],
        ["Invoice date:", inv.invoice_date],
    ]
    if inv.due_date:
        meta_rows.append(["Due date:", inv.due_date])
    meta_rows.append(["Bill to:", inv.bill_to])

    meta = Table(meta_rows, colWidths=[1.2 * inch, 5.6 * inch])
    meta.setStyle(TableStyle([
        ("FONT", (0, 0), (0, -1), "Helvetica-Bold"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(meta)
    story.append(Spacer(1, 0.25 * inch))

    # Line items table
    table_data = [["Description", "Qty", "Unit Price", "Total"]]
    for li in inv.line_items:
        table_data.append([
            li.description,
            f"{li.qty:g}",
            f"${li.unit_price:,.2f}",
            f"${li.total:,.2f}",
        ])
    items = Table(table_data, colWidths=[4.0 * inch, 0.8 * inch, 1.0 * inch, 1.0 * inch])
    items.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#0f172a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f1f5f9")]),
    ]))
    story.append(items)
    story.append(Spacer(1, 0.15 * inch))

    # Totals
    subtotal = inv.printed_subtotal if inv.printed_subtotal is not None else inv.subtotal
    tax = inv.printed_tax if inv.printed_tax is not None else inv.tax
    total = inv.printed_total if inv.printed_total is not None else inv.total
    tax_rate_str = f"{inv.tax_rate*100:.1f}%" if inv.tax_rate else "0.0%"

    totals_data = [
        ["", "Subtotal", f"${subtotal:,.2f}"],
        ["", f"Tax ({tax_rate_str})", f"${tax:,.2f}"],
        ["", "TOTAL DUE", f"${total:,.2f}"],
    ]
    totals = Table(totals_data, colWidths=[4.8 * inch, 1.0 * inch, 1.0 * inch])
    totals.setStyle(TableStyle([
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("FONT", (1, -1), (-1, -1), "Helvetica-Bold"),
        ("LINEABOVE", (1, -1), (-1, -1), 1.2, colors.black),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("FONTSIZE", (1, -1), (-1, -1), 12),
    ]))
    story.append(totals)
    story.append(Spacer(1, 0.4 * inch))

    if inv.notes:
        story.append(Paragraph(f"<i>{inv.notes}</i>", small))

    story.append(Spacer(1, 0.6 * inch))
    story.append(Paragraph(
        "Thank you for your business. Payment is due per the date shown above. "
        "Questions? Reply to the email this invoice was attached to.",
        small,
    ))

    doc.build(story)


# ---------------------------------------------------------------------------
# Invoice definitions
# ---------------------------------------------------------------------------

BILL_TO = "Acme SaaS Inc.\n2120 University Ave, Berkeley, CA 94704"

INVOICES = [
    Invoice(
        filename="01_aws_apr.pdf",
        vendor_name="Amazon Web Services",
        vendor_address="410 Terry Avenue North, Seattle, WA 98109",
        bill_to=BILL_TO,
        invoice_number="AWS-2026-0418",
        invoice_date="2026-04-30",
        due_date="2026-05-30",
        line_items=[
            LineItem("EC2 compute (t3.large, 720 hrs)", 720, 0.0832),
            LineItem("S3 storage (1.2 TB)", 1.2, 23.00),
            LineItem("Data transfer out (180 GB)", 180, 0.09),
            LineItem("RDS Postgres (db.t3.small, 720 hrs)", 720, 0.034),
        ],
        tax_rate=0.0,
        notes="AWS bills are tax-inclusive in your region.",
    ),
    Invoice(
        filename="02_stripe_apr.pdf",
        vendor_name="Stripe, Inc.",
        vendor_address="510 Townsend Street, San Francisco, CA 94103",
        bill_to=BILL_TO,
        invoice_number="STR-INV-447821",
        invoice_date="2026-04-30",
        due_date="2026-05-15",
        line_items=[
            LineItem("Payment processing fees (April)", 1, 1247.55),
            LineItem("Dispute fees (3 disputes)", 3, 15.00),
            LineItem("International transaction surcharge", 1, 84.20),
        ],
        tax_rate=0.0,
    ),
    Invoice(
        filename="03_notion_may.pdf",
        vendor_name="Notion Labs, Inc.",
        vendor_address="2300 Harrison Street, San Francisco, CA 94110",
        bill_to=BILL_TO,
        invoice_number="NOT-2025-1042",
        invoice_date="2026-05-01",
        due_date="2026-05-31",
        line_items=[
            LineItem("Business plan, 24 seats (monthly)", 24, 18.00),
        ],
        tax_rate=0.0875,
    ),
    Invoice(
        filename="04_notion_jun.pdf",
        vendor_name="Notion Labs, Inc.",
        vendor_address="2300 Harrison Street, San Francisco, CA 94110",
        bill_to=BILL_TO,
        invoice_number="NOT-2025-1042",  # DUPLICATE — same number as 03
        invoice_date="2026-06-01",
        due_date="2026-06-30",
        line_items=[
            LineItem("Business plan, 26 seats (monthly)", 26, 18.00),
        ],
        tax_rate=0.0875,
    ),
    Invoice(
        filename="05_adobe_q2.pdf",
        vendor_name="Adobe Inc.",
        vendor_address="345 Park Avenue, San Jose, CA 95110",
        bill_to=BILL_TO,
        invoice_number="ADBE-Q2-2026-88412",
        invoice_date="2026-04-15",
        due_date="2026-05-15",
        line_items=[
            LineItem("Creative Cloud All Apps (annual prepay, 6 seats)", 6, 599.88),
            LineItem("Stock images credit pack", 1, 240.00),
        ],
        tax_rate=0.0875,
    ),
    Invoice(
        filename="06_wework_may.pdf",
        vendor_name="WeWork Companies LLC",
        vendor_address="115 W 18th St, New York, NY 10011",
        bill_to=BILL_TO,
        invoice_number="WW-SF-2026-05-0094",
        invoice_date="2026-05-01",
        due_date="2026-05-10",
        line_items=[
            LineItem("Private office (4 desks, May 2026)", 1, 3850.00),
            LineItem("Meeting room credits (overage)", 12, 25.00),
            LineItem("Mailroom and printing", 1, 45.00),
        ],
        tax_rate=0.0875,
    ),
    Invoice(
        filename="07_supplies_misc.pdf",
        vendor_name="Misc Supplier",  # Vague vendor name
        vendor_address="No address on file",
        bill_to=BILL_TO,
        invoice_number="SUPPLY-2025-007",
        invoice_date="2026-05-08",
        due_date="2026-05-22",
        line_items=[
            LineItem("Office chairs (Herman Miller refurb)", 4, 425.00),
            LineItem("Standing desk converters", 2, 220.00),
            LineItem("Whiteboard, 6'x4'", 1, 380.00),
        ],
        tax_rate=0.0875,
        # MATH ERROR — printed total is wrong. Line items: 1700 + 440 + 380 = 2520
        # Subtotal *should* be 2520; tax 220.50; total 2740.50.
        # But printed values disagree.
        printed_subtotal=2520.00,
        printed_tax=220.50,
        printed_total=3245.50,  # ← inflated by ~$505
        notes="Net 14. Wire transfer instructions on file.",
    ),
    Invoice(
        filename="08_linode_apr.pdf",
        vendor_name="Linode (Akamai Technologies)",
        vendor_address="249 Arch Street, Philadelphia, PA 19106",
        bill_to=BILL_TO,
        invoice_number="INV-90217",
        invoice_date="2026-04-30",
        due_date=None,  # MISSING due date
        line_items=[
            LineItem("Dedicated CPU 4GB (3 nodes, 720 hrs)", 3, 36.00),
            LineItem("Backups", 1, 12.00),
            LineItem("Object storage (250 GB)", 1, 5.00),
        ],
        tax_rate=0.0,
    ),
]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for inv in INVOICES:
        path = OUTPUT_DIR / inv.filename
        render_invoice(inv, path)
        printed_total = inv.printed_total if inv.printed_total is not None else inv.total
        print(f"  Wrote {path.name}  ({inv.vendor_name}, ${printed_total:,.2f})")
    print(f"\n{len(INVOICES)} sample PDFs written to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
