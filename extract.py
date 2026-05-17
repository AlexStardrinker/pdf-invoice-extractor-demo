"""
PDF invoices → Claude extraction → structured CSV + anomaly report
-----------------------------------------------------------------
Reads a folder of PDF invoices, asks Claude to extract a strict schema
(vendor, invoice number, dates, line items, totals), validates each
extraction with a deterministic rule set, and emits two deliverables:

  output/extracted_invoices.csv   — the data, normalized
  output/anomaly_report.md        — the small set of bills a human should look at

This file is the demo entry point. It runs end-to-end on bundled sample
PDFs with zero credentials, and is wired so swapping in real Claude API
access is a 5-line change (see README).

Author: Lucas A. (portfolio sample)
"""
from __future__ import annotations

import base64
import csv
import json
import os
import re
import sys
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Optional

import pdfplumber  # type: ignore

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).parent
INPUT_DIR = PROJECT_ROOT / "sample_pdfs"
OUTPUT_DIR = PROJECT_ROOT / "output"
OUTPUT_CSV = OUTPUT_DIR / "extracted_invoices.csv"
OUTPUT_REPORT = OUTPUT_DIR / "anomaly_report.md"

USE_REAL_CLAUDE = bool(os.environ.get("ANTHROPIC_API_KEY"))

# Validation thresholds
MATH_TOLERANCE = 0.05  # 5 cents — accounts for rounding
VAGUE_VENDOR_PATTERNS = [
    re.compile(r"\bmisc\b", re.IGNORECASE),
    re.compile(r"\bsupplier\b\s*$", re.IGNORECASE),
    re.compile(r"^vendor$", re.IGNORECASE),
    re.compile(r"^unknown", re.IGNORECASE),
]


# ---------------------------------------------------------------------------
# Data shapes
# ---------------------------------------------------------------------------


@dataclass
class LineItem:
    description: str
    qty: float
    unit_price: float
    total: float


@dataclass
class ExtractedInvoice:
    source_file: str
    vendor_name: str
    invoice_number: str
    invoice_date: str
    due_date: str
    subtotal: float
    tax: float
    total: float
    line_items: list[LineItem] = field(default_factory=list)
    # Filled by validation
    anomalies: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.anomalies


# ---------------------------------------------------------------------------
# Step 1 — Read the PDF
# ---------------------------------------------------------------------------


def read_pdf_text(path: Path) -> str:
    """Pull plain text out of the PDF. pdfplumber preserves layout reasonably
    well; in production you'd hand the raw bytes to Claude as multimodal
    input instead (Claude can read PDFs natively)."""
    with pdfplumber.open(path) as pdf:
        return "\n".join(page.extract_text() or "" for page in pdf.pages)


# ---------------------------------------------------------------------------
# Step 2 — Extract structured fields with Claude
# ---------------------------------------------------------------------------

EXTRACTION_PROMPT = """You are an accounts-payable assistant.
Extract the following fields from the invoice text below and return STRICT
JSON. If a field is missing, return an empty string for text or null for a
number; do not invent values.

Schema:
{
  "vendor_name": str,
  "invoice_number": str,
  "invoice_date": str (ISO 8601 YYYY-MM-DD if possible),
  "due_date": str | "",
  "subtotal": number | null,
  "tax": number | null,
  "total": number | null,
  "line_items": [
    {"description": str, "qty": number, "unit_price": number, "total": number}
  ]
}

Invoice text:
---
{invoice_text}
---
"""


def extract_with_claude(pdf_path: Path, text: str) -> dict:
    """Call Claude to extract structured data. Falls back to mock parser."""
    if USE_REAL_CLAUDE:
        from anthropic import Anthropic  # type: ignore

        client = Anthropic()
        pdf_b64 = base64.standard_b64encode(pdf_path.read_bytes()).decode()
        message = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "document", "source": {
                        "type": "base64", "media_type": "application/pdf", "data": pdf_b64,
                    }},
                    {"type": "text", "text": EXTRACTION_PROMPT.replace(
                        "{invoice_text}", "(see attached PDF)"
                    )},
                ],
            }],
        )
        return json.loads(message.content[0].text)

    return _mock_extract(text)


# ---------------------------------------------------------------------------
# Mock extractor (regex-driven stand-in for Claude)
# ---------------------------------------------------------------------------


_MONEY_RE = re.compile(r"\$?([\d,]+\.\d{2})")
_DATE_RE = re.compile(r"\b(20\d{2}-\d{2}-\d{2})\b")


def _money(s: str) -> Optional[float]:
    m = _MONEY_RE.search(s)
    if not m:
        return None
    return float(m.group(1).replace(",", ""))


def _mock_extract(text: str) -> dict:
    """Deterministic stand-in for Claude that mirrors the same output shape."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # First line is "<Vendor Name>   INVOICE" because of the header table layout.
    vendor_name = re.sub(r"\s+INVOICE\s*$", "", lines[0]) if lines else ""

    invoice_number = _grab_field(text, r"Invoice\s*#:\s*([^\s].*?)$")
    invoice_date = _grab_field(text, r"Invoice date:\s*(20\d{2}-\d{2}-\d{2})")
    due_date_match = re.search(r"Due date:\s*(20\d{2}-\d{2}-\d{2})", text)
    due_date = due_date_match.group(1) if due_date_match else ""

    subtotal = _grab_money_after(text, r"Subtotal")
    tax = _grab_money_after(text, r"Tax")
    total = _grab_money_after(text, r"TOTAL DUE")

    line_items = _parse_line_items(text)

    return {
        "vendor_name": vendor_name,
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "subtotal": subtotal,
        "tax": tax,
        "total": total,
        "line_items": line_items,
    }


def _grab_field(text: str, pattern: str) -> str:
    m = re.search(pattern, text, flags=re.MULTILINE)
    return m.group(1).strip() if m else ""


def _grab_money_after(text: str, label_pattern: str) -> Optional[float]:
    for line in text.splitlines():
        if re.search(label_pattern, line):
            return _money(line)
    return None


def _parse_line_items(text: str) -> list[dict]:
    """Pull rows out of the items table. The bundled PDFs use a consistent
    Description / Qty / Unit Price / Total layout."""
    items: list[dict] = []
    in_table = False
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("Description") and "Qty" in stripped:
            in_table = True
            continue
        if not in_table:
            continue
        if stripped.startswith("Subtotal"):
            break
        # rows look like:   "Description text   720   $0.08   $59.90"
        m = re.match(r"^(.*?)\s+([\d.]+)\s+\$?([\d,]+\.\d{2})\s+\$?([\d,]+\.\d{2})$", stripped)
        if m:
            items.append({
                "description": m.group(1).strip(),
                "qty": float(m.group(2)),
                "unit_price": float(m.group(3).replace(",", "")),
                "total": float(m.group(4).replace(",", "")),
            })
    return items


# ---------------------------------------------------------------------------
# Step 3 — Validate
# ---------------------------------------------------------------------------


def validate(inv: ExtractedInvoice, seen_invoice_numbers: dict[tuple[str, str], str]) -> None:
    """Append human-actionable anomaly notes to inv.anomalies."""

    # Required fields
    if not inv.due_date:
        inv.anomalies.append("Missing due date")
    if any(p.search(inv.vendor_name) for p in VAGUE_VENDOR_PATTERNS):
        inv.anomalies.append(f"Vague vendor name: '{inv.vendor_name}'")

    # Math reconciliation: do the line items actually sum to the printed subtotal?
    if inv.line_items and inv.subtotal is not None:
        computed = round(sum(li.total for li in inv.line_items), 2)
        if abs(computed - inv.subtotal) > MATH_TOLERANCE:
            inv.anomalies.append(
                f"Math mismatch: line items sum to ${computed:,.2f}, "
                f"printed subtotal is ${inv.subtotal:,.2f}"
            )

    # Does subtotal + tax = total?
    if inv.subtotal is not None and inv.tax is not None and inv.total is not None:
        if abs((inv.subtotal + inv.tax) - inv.total) > MATH_TOLERANCE:
            inv.anomalies.append(
                f"Math mismatch: subtotal (${inv.subtotal:,.2f}) + tax (${inv.tax:,.2f}) "
                f"= ${inv.subtotal + inv.tax:,.2f}, but printed total is ${inv.total:,.2f}"
            )

    # Duplicate invoice number from the same vendor (likely double-billing)
    key = (inv.vendor_name, inv.invoice_number)
    if key in seen_invoice_numbers:
        inv.anomalies.append(
            f"Duplicate invoice number from {inv.vendor_name} — also appears in "
            f"{seen_invoice_numbers[key]}"
        )
    else:
        seen_invoice_numbers[key] = inv.source_file


# ---------------------------------------------------------------------------
# Step 4 — Write outputs
# ---------------------------------------------------------------------------


def write_csv(rows: list[ExtractedInvoice], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "source_file", "vendor_name", "invoice_number",
            "invoice_date", "due_date", "subtotal", "tax", "total",
            "line_item_count", "anomaly_count", "anomalies",
        ])
        for r in rows:
            writer.writerow([
                r.source_file, r.vendor_name, r.invoice_number,
                r.invoice_date, r.due_date,
                f"{r.subtotal:.2f}" if r.subtotal is not None else "",
                f"{r.tax:.2f}" if r.tax is not None else "",
                f"{r.total:.2f}" if r.total is not None else "",
                len(r.line_items),
                len(r.anomalies),
                " | ".join(r.anomalies),
            ])


def write_anomaly_report(rows: list[ExtractedInvoice], path: Path) -> None:
    flagged = [r for r in rows if r.anomalies]
    clean = [r for r in rows if not r.anomalies]

    lines = [
        f"# Invoice Extraction Report",
        "",
        f"**Processed:** {len(rows)} invoices  ",
        f"**Clean:** {len(clean)}  ",
        f"**Flagged for review:** {len(flagged)}  ",
        "",
    ]

    if flagged:
        lines.append("## :warning: Invoices needing human review")
        lines.append("")
        for r in flagged:
            lines.append(f"### `{r.source_file}` — {r.vendor_name}")
            lines.append(
                f"Invoice #{r.invoice_number} · "
                f"Total ${r.total:,.2f}" if r.total else f"Invoice #{r.invoice_number}"
            )
            lines.append("")
            for a in r.anomalies:
                lines.append(f"- {a}")
            lines.append("")
    else:
        lines.append(":white_check_mark: No anomalies — all invoices look clean.")
        lines.append("")

    if clean:
        lines.append("## Clean invoices")
        lines.append("")
        lines.append("| File | Vendor | Invoice # | Total | Due |")
        lines.append("|------|--------|-----------|-------|-----|")
        for r in clean:
            total_str = f"${r.total:,.2f}" if r.total else "—"
            lines.append(
                f"| `{r.source_file}` | {r.vendor_name} | {r.invoice_number} | "
                f"{total_str} | {r.due_date or '—'} |"
            )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    pdfs = sorted(INPUT_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"No PDFs found in {INPUT_DIR}", file=sys.stderr)
        return 1

    print(f"Found {len(pdfs)} PDF(s) in {INPUT_DIR.name}/")
    mode_msg = "real Claude API" if USE_REAL_CLAUDE else "mock parser (set ANTHROPIC_API_KEY for real run)"
    print(f"Extracting with {mode_msg}")

    extracted: list[ExtractedInvoice] = []
    for pdf in pdfs:
        text = read_pdf_text(pdf)
        data = extract_with_claude(pdf, text)
        inv = ExtractedInvoice(
            source_file=pdf.name,
            vendor_name=data.get("vendor_name", ""),
            invoice_number=data.get("invoice_number", ""),
            invoice_date=data.get("invoice_date", ""),
            due_date=data.get("due_date", ""),
            subtotal=data.get("subtotal"),
            tax=data.get("tax"),
            total=data.get("total"),
            line_items=[LineItem(**li) for li in data.get("line_items", [])],
        )
        extracted.append(inv)
        print(f"  · {pdf.name:32s} {inv.vendor_name[:30]:30s} ${inv.total or 0:>10,.2f}")

    print("\nValidating...")
    seen: dict[tuple[str, str], str] = {}
    for inv in extracted:
        validate(inv, seen)
        if inv.anomalies:
            print(f"  ⚠  {inv.source_file}: {len(inv.anomalies)} issue(s)")

    write_csv(extracted, OUTPUT_CSV)
    write_anomaly_report(extracted, OUTPUT_REPORT)

    flagged = sum(1 for inv in extracted if inv.anomalies)
    print(f"\nWrote {OUTPUT_CSV.name} and {OUTPUT_REPORT.name}")
    print(f"{flagged}/{len(extracted)} invoices flagged for review")
    return 0


if __name__ == "__main__":
    sys.exit(main())
