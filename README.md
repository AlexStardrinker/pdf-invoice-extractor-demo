# PDF Invoices → Claude → CSV + anomaly report

A Python automation that turns a folder of PDF invoices into a clean, structured
spreadsheet — with Claude doing the extraction and a deterministic rule set
flagging the small subset of bills a human should actually look at.

This is a **portfolio sample** demonstrating a class of automation I build for
clients: process a stream of unstructured documents, extract whatever schema
they ask for, validate it, and put the output somewhere they can act on. The
demo runs end-to-end on 8 bundled sample PDFs with zero credentials. Swapping
in real Claude API access is a 5-line change documented below.

---

## What it does

Every time a buyer drops new PDF invoices into `sample_pdfs/`, the script:

1. **Reads each PDF** (pdfplumber for layout-aware text, plus the full bytes
   are passed to Claude as multimodal input in production mode).
2. **Asks Claude to extract a strict schema** — vendor, invoice number, dates,
   line items, subtotal, tax, total.
3. **Runs a deterministic validation pass** alongside the LLM so anomalies
   are auditable, not just AI-asserted:
   - Math reconciliation: line items must sum to subtotal, subtotal + tax must
     equal total (5-cent tolerance for rounding).
   - Duplicate detection: same invoice number from the same vendor across
     different files (a classic double-billing signal).
   - Missing required fields: due date, vendor.
   - Vague vendor names ("Misc Supplier", "Unknown Vendor", etc.).
4. **Writes `output/extracted_invoices.csv`** — one row per invoice, ready to
   import into Xero, QuickBooks, or a Google Sheet.
5. **Writes `output/anomaly_report.md`** — the bills that need human review,
   grouped and explained in plain English.

## Example output (from the bundled sample PDFs)

```
**Processed:** 8 invoices
**Clean:** 5
**Flagged for review:** 3

⚠ 04_notion_jun.pdf — Notion Labs, Inc.
  Invoice #NOT-2025-1042 · Total $508.95
  - Duplicate invoice number from Notion Labs, Inc. — also appears in 03_notion_may.pdf

⚠ 07_supplies_misc.pdf — Misc Supplier
  Invoice #SUPPLY-2025-007 · Total $3,245.50
  - Vague vendor name: 'Misc Supplier'
  - Math mismatch: subtotal ($2,520.00) + tax ($220.50) = $2,740.50,
    but printed total is $3,245.50

⚠ 08_linode_apr.pdf — Linode (Akamai Technologies)
  Invoice #INV-90217 · Total $125.00
  - Missing due date
```

The three flagged bills are exactly the ones a finance person should look at:
a likely double-billing, a $505 math discrepancy you'd otherwise pay without
noticing, and a missing due date that breaks your AP scheduling.

The other 5 invoices, including a $4,562 WeWork bill and a $4,175 Adobe
prepay, are correctly categorized and reconciled without noise.

## Run the demo

```bash
git clone <this repo>
cd pdf-invoice-extractor-demo
pip install -r requirements.txt
python3 extract.py
```

That's it — no API keys needed for the demo. Outputs land in `output/`.

To regenerate the sample PDFs (you'd never do this in production, this is
just so the demo is reproducible):

```bash
python3 scripts/generate_sample_invoices.py
```

## Wire up real Claude

Set `ANTHROPIC_API_KEY` in your environment and the script swaps automatically
from the deterministic mock parser to a real Claude call. The real call passes
the entire PDF to Claude as a multimodal document, which handles scans, weird
layouts, multi-page invoices, and non-English bills that regex-based extraction
would mangle.

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python3 extract.py
```

## Project layout

```
pdf-invoice-extractor-demo/
├── extract.py                          # Main script
├── scripts/
│   └── generate_sample_invoices.py     # Recreates the bundled PDFs
├── sample_pdfs/                        # 8 realistic invoice samples
├── output/
│   ├── extracted_invoices.csv          # Normalized data (gets written here)
│   └── anomaly_report.md               # Human-readable review queue
├── requirements.txt
└── README.md
```

## Design notes

A few decisions worth calling out, since they're the kind of choices clients
hire for:

- **AI extraction is paired with deterministic validation.** Claude is good at
  pulling fields out of weird layouts, but it can also hallucinate a number.
  Math reconciliation, duplicate detection, and required-field checks are pure
  Python — they don't trust the LLM, they audit it.
- **The mock parser is a feature.** The demo runs anywhere without API keys,
  and the regex-based extractor doubles as offline testing infrastructure
  when iterating on validation logic.
- **PDFs are passed to Claude as documents, not as extracted text.** Real
  invoices have logos, tables, footers, scanned pages. Pre-extracting text
  with pdfplumber would lose layout signal that Claude uses to disambiguate
  fields. The bundled mock parser is the simplified version; production uses
  the multimodal path.

## What I'd build next (for a real client)

These weren't included to keep the demo tight, but are how I'd extend it on
a paid engagement:

- **Email auto-ingestion** — IMAP poller that pulls PDF attachments from a
  dedicated invoices@ address and drops them into `sample_pdfs/` automatically.
- **Direct accounting integration** — push extracted rows straight into Xero,
  QuickBooks, or a shared Google Sheet via their API.
- **Vendor allowlist** — flag any invoice from a vendor not on the approved
  payee list (catches phishing invoices that get past email filters).
- **Currency handling** — auto-detect non-USD bills and convert at the
  invoice date's exchange rate for consistent reporting.
- **Per-line GL coding** — Claude suggests an accounting category for each
  line item based on the buyer's chart of accounts.

---

**Built by Lucas A.** — data analyst & Python automation specialist.
Available on Fiverr for similar automations: document processing, data
pipelines, scheduled scrapers, report generation, AI-enriched workflows.
