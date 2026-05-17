# Invoice Extraction Report

**Processed:** 8 invoices  
**Clean:** 5  
**Flagged for review:** 3  

## :warning: Invoices needing human review

### `04_notion_jun.pdf` — Notion Labs, Inc.
Invoice #NOT-2025-1042 · Total $508.95

- Duplicate invoice number from Notion Labs, Inc. — also appears in 03_notion_may.pdf

### `07_supplies_misc.pdf` — Misc Supplier
Invoice #SUPPLY-2025-007 · Total $3,245.50

- Vague vendor name: 'Misc Supplier'
- Math mismatch: subtotal ($2,520.00) + tax ($220.50) = $2,740.50, but printed total is $3,245.50

### `08_linode_apr.pdf` — Linode (Akamai Technologies)
Invoice #INV-90217 · Total $125.00

- Missing due date

## Clean invoices

| File | Vendor | Invoice # | Total | Due |
|------|--------|-----------|-------|-----|
| `01_aws_apr.pdf` | Amazon Web Services | AWS-2026-0418 | $128.18 | 2026-05-30 |
| `02_stripe_apr.pdf` | Stripe, Inc. | STR-INV-447821 | $1,376.75 | 2026-05-15 |
| `03_notion_may.pdf` | Notion Labs, Inc. | NOT-2025-1042 | $469.80 | 2026-05-31 |
| `05_adobe_q2.pdf` | Adobe Inc. | ADBE-Q2-2026-88412 | $4,175.22 | 2026-05-15 |
| `06_wework_may.pdf` | WeWork Companies LLC | WW-SF-2026-05-0094 | $4,562.06 | 2026-05-10 |
