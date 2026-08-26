#!/usr/bin/env python3
"""Fetch, parse, and stage SEC EDGAR 10-K & 10-Q corporate financial filings.

SEC EDGAR annual (10-K) and quarterly (10-Q) filings represent tens of millions
of tokens of high-value structured legal and financial engineering data (50M - 500M tokens).

This script extracts:
- Item sections (Item 1 Business, Item 1A Risk Factors, Item 7 MD&A, Item 8 Financials)
- Tables parsed into structured Markdown tables
- Regulatory risk disclosures and hierarchical document tree metadata
- SEC company CIK, ticker, period of report, and filing metadata

Supports:
- SEC EDGAR API fetching with rate limiting & compliant User-Agent headers
- Parsing local HTML/HTM filing files
- --dry-run for offline verification and schema testing
- --limit <N> for bounded ingestion
- Standard Phase 1 JSONL output
"""

from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import time
import urllib.request
from collections.abc import Generator
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Support execution both as script and module
try:
    from .common import (
        DEFAULT_SCALE_DATA_ROOT,
        clean_text_whitespace,
        create_trace_record,
        get_default_staging_dir,
        write_jsonl_records,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from scripts.scale_datasets.common import (
        DEFAULT_SCALE_DATA_ROOT,
        clean_text_whitespace,
        create_trace_record,
        get_default_staging_dir,
        write_jsonl_records,
    )

DEFAULT_USER_AGENT = "TraceResearch research@trace-local.org"

# Prominent SEC 10-K Item Sections
SEC_10K_ITEMS = [
    ("item1", r"ITEM\s+1\.\s+BUSINESS", "Item 1. Business"),
    ("item1a", r"ITEM\s+1A\.\s+RISK\s+FACTORS", "Item 1A. Risk Factors"),
    ("item1b", r"ITEM\s+1B\.\s+UNRESOLVED\s+STAFF\s+COMMENTS", "Item 1B. Unresolved Staff Comments"),
    ("item1c", r"ITEM\s+1C\.\s+CYBERSECURITY", "Item 1C. Cybersecurity"),
    ("item2", r"ITEM\s+2\.\s+PROPERTIES", "Item 2. Properties"),
    ("item3", r"ITEM\s+3\.\s+LEGAL\s+PROCEEDINGS", "Item 3. Legal Proceedings"),
    ("item5", r"ITEM\s+5\.\s+MARKET\s+FOR\s+REGISTRANT", "Item 5. Market for Common Equity"),
    ("item7", r"ITEM\s+7\.\s+MANAGEMENT\'?S\s+DISCUSSION\s+AND\s+ANALYSIS", "Item 7. Management's Discussion and Analysis"),
    ("item7a", r"ITEM\s+7A\.\s+QUANTITATIVE\s+AND\s+QUALITATIVE", "Item 7A. Quantitative and Qualitative Disclosures"),
    ("item8", r"ITEM\s+8\.\s+FINANCIAL\s+STATEMENTS", "Item 8. Financial Statements"),
    ("item9a", r"ITEM\s+9A\.\s+CONTROLS\s+AND\s+PROCEDURES", "Item 9A. Controls and Procedures"),
]


def html_table_to_markdown(table_html: str) -> str:
    """Convert an HTML table fragment into a clean Markdown table."""
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(table_html, "html.parser")
    except ImportError:
        # Fallback regex-based simple cleaner if bs4 not available
        clean = re.sub(r"<[^>]+>", " ", table_html)
        return clean_text_whitespace(clean)

    rows: list[list[str]] = []
    for tr in soup.find_all("tr"):
        cols = [clean_text_whitespace(td.get_text(separator=" ")) for td in tr.find_all(["td", "th"])]
        if any(cols):
            rows.append(cols)

    if not rows:
        return ""

    # Normalize column lengths
    max_cols = max(len(r) for r in rows)
    normalized_rows = [r + [""] * (max_cols - len(r)) for r in rows]

    header = normalized_rows[0]
    separator = ["---"] * max_cols
    body = normalized_rows[1:]

    lines = [
        "| " + " | ".join(header) + " |",
        "| " + " | ".join(separator) + " |",
    ]
    for row in body:
        lines.append("| " + " | ".join(row) + " |")

    return "\n".join(lines)


def clean_sec_html(raw_html: str) -> str:
    """Strip XML/HTML markup, styles, and scripts while preserving text structure."""
    text = re.sub(r"<style[\s\S]*?</style>", "", raw_html, flags=re.IGNORECASE)
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<ix:[\s\S]*?>", "", text, flags=re.IGNORECASE)
    # Replace block level tags with newlines
    text = re.sub(r"</?(?:p|div|tr|h\d|br)[\s\S]*?>", "\n", text, flags=re.IGNORECASE)
    # Replace remaining tags
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return clean_text_whitespace(text)


def segment_filing_sections(
    doc_text: str,
    metadata_base: dict[str, Any],
) -> list[dict[str, Any]]:
    """Segment a filing text into hierarchical Item sections."""
    sections: list[dict[str, Any]] = []

    # Find offsets for each item
    matches: list[tuple[int, str, str, str]] = []
    for item_id, pattern, item_title in SEC_10K_ITEMS:
        m = re.search(pattern, doc_text, flags=re.IGNORECASE)
        if m:
            matches.append((m.start(), item_id, item_title, m.group(0)))

    matches.sort(key=lambda x: x[0])

    if not matches:
        # Single document if no item headers detected
        doc_name = f"edgar/{metadata_base.get('ticker', 'SEC')}/{metadata_base.get('accession_number', 'doc')}/full"
        return [
            create_trace_record(
                document_name=doc_name,
                content=doc_text,
                source_uri=metadata_base.get("source_url", f"sec://{doc_name}"),
                metadata={**metadata_base, "section_id": "full", "section_title": "Full Filing"},
                collection="edgar",
            )
        ]

    for i in range(len(matches)):
        start_idx, item_id, item_title, raw_header = matches[i]
        end_idx = matches[i + 1][0] if i + 1 < len(matches) else len(doc_text)
        section_content = clean_text_whitespace(doc_text[start_idx:end_idx])

        if len(section_content) < 50:
            continue

        doc_name = (
            f"edgar/{metadata_base.get('ticker', 'SEC')}/"
            f"{metadata_base.get('fiscal_year', 'FY')}_{metadata_base.get('form_type', '10K')}/"
            f"{item_id}"
        )

        section_meta = {
            **metadata_base,
            "section_id": item_id,
            "section_title": item_title,
            "raw_header": raw_header,
            "char_length": len(section_content),
            "hierarchy": {
                "parent_doc": f"{metadata_base.get('ticker', 'SEC')}_{metadata_base.get('form_type', '10K')}_{metadata_base.get('fiscal_year', 'FY')}",
                "level": 1,
                "item": item_id,
            },
        }

        # Extract risk clause count if Item 1A
        if item_id == "item1a":
            risk_headings = re.findall(r"\n([A-Z][A-Za-z0-9\s,\-\'\"]{10,120}\.\s*\n)", section_content)
            section_meta["risk_clause_count"] = len(risk_headings)

        sections.append(
            create_trace_record(
                document_name=doc_name,
                content=f"# {item_title}\n\n{section_content}",
                source_uri=metadata_base.get("source_url", f"sec://{doc_name}"),
                metadata=section_meta,
                collection="edgar",
            )
        )

    return sections


def generate_synthetic_edgar_records(count: int = 12) -> Generator[dict[str, Any], None, None]:
    """Generate realistic SEC EDGAR 10-K & 10-Q corporate reports."""
    filings = [
        {
            "ticker": "NVDA",
            "company_name": "NVIDIA CORPORATION",
            "cik": "0001045810",
            "form_type": "10-K",
            "fiscal_year": "2024",
            "fiscal_period": "FY",
            "filing_date": "2024-02-21",
            "accession_number": "0001045810-24-000029",
            "sections": [
                {
                    "item_id": "item1",
                    "title": "Item 1. Business",
                    "text": (
                        "ITEM 1. BUSINESS\n\n"
                        "Overview\n"
                        "NVIDIA pioneered accelerated computing to tackle challenges that ordinary computers cannot solve. "
                        "Our work in AI and computer graphics is transforming industries from healthcare to automotive and robotics. "
                        "Our computing platform consists of hardware including accelerated GPUs, DPUs, and CPUs, interconnects, "
                        "and software including NVIDIA CUDA, CUDA-X, NVIDIA AI Enterprise, and Omniverse.\n\n"
                        "Data Center Architecture\n"
                        "Our Data Center architecture delivers full-stack accelerated computing platforms, integrating "
                        "Grace Hopper Superchips, Blackwell GPUs, NVLink quantum switches, and Spectrum-X networking fabrics."
                    ),
                },
                {
                    "item_id": "item1a",
                    "title": "Item 1A. Risk Factors",
                    "text": (
                        "ITEM 1A. RISK FACTORS\n\n"
                        "Risks Related to Our Supply Chain and Manufacturing\n"
                        "We rely on a limited number of third-party foundries, primarily TSMC, to produce our advanced silicon wafers. "
                        "Failure to obtain sufficient advanced packaging capacity (such as CoWoS) or disruptions in the Taiwan Strait "
                        "could materially constrain our ability to satisfy customer demand for our Hopper and Blackwell platforms.\n\n"
                        "Export Controls and Geopolitical Uncertainties\n"
                        "The U.S. Department of Commerce Bureau of Industry and Security (BIS) has enacted licensing requirements "
                        "and total processing performance thresholds for advanced integrated circuits exported to China and other "
                        "Designated Regions. These regulations limit our addressable market for high-performance AI accelerators."
                    ),
                },
                {
                    "item_id": "item7",
                    "title": "Item 7. Management's Discussion and Analysis (MD&A)",
                    "text": (
                        "ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION AND RESULTS OF OPERATIONS\n\n"
                        "Fiscal Year 2024 Financial Highlights\n"
                        "Revenue for fiscal year 2024 was $60.92 billion, up 126% from $26.97 billion in fiscal year 2023. "
                        "Data Center revenue surged 217% to $47.53 billion, driven by surging demand for the NVIDIA HGX platform "
                        "and accelerated computing infrastructure among hyperscalers and enterprise software companies.\n\n"
                        "| Segment | FY2024 ($M) | FY2023 ($M) | YoY Growth |\n"
                        "| --- | --- | --- | --- |\n"
                        "| Data Center | 47,525 | 15,013 | +217% |\n"
                        "| Gaming | 10,447 | 9,067 | +15% |\n"
                        "| Professional Visualization | 1,553 | 1,544 | +1% |\n"
                        "| Automotive | 1,091 | 903 | +21% |\n"
                        "| Total Revenue | 60,922 | 26,974 | +126% |"
                    ),
                },
            ],
        },
        {
            "ticker": "AAPL",
            "company_name": "APPLE INC.",
            "cik": "0000320193",
            "form_type": "10-K",
            "fiscal_year": "2024",
            "fiscal_period": "FY",
            "filing_date": "2024-10-31",
            "accession_number": "0000320193-24-000106",
            "sections": [
                {
                    "item_id": "item1a",
                    "title": "Item 1A. Risk Factors",
                    "text": (
                        "ITEM 1A. RISK FACTORS\n\n"
                        "Global Economic and Antitrust Regulatory Scrutiny\n"
                        "The Company is subject to complex and evolving laws and regulations globally regarding privacy, "
                        "data protection, digital markets, App Store distribution models, and interoperability mandates "
                        "(including the EU Digital Markets Act). Compliance requirements may alter our commercial terms "
                        "and fee structures.\n\n"
                        "Custom Silicon Integration and Foundry Dependencies\n"
                        "The Company relies on proprietary Apple Silicon (M-series and A-series processors). Any yield issues "
                        "or manufacturing bottlenecks at leading 3nm semiconductor fabrication nodes may delay product launches."
                    ),
                },
                {
                    "item_id": "item7",
                    "title": "Item 7. Management's Discussion and Analysis (MD&A)",
                    "text": (
                        "ITEM 7. MANAGEMENT'S DISCUSSION AND ANALYSIS OF FINANCIAL CONDITION\n\n"
                        "Total net sales increased 2% to $391.0 billion in fiscal 2024 compared to $383.3 billion in fiscal 2023. "
                        "Services revenue reached an all-time record of $96.2 billion, reflecting continuous expansion of paid "
                        "subscriptions across iCloud, Apple Music, and payment services.\n\n"
                        "| Category | FY2024 ($M) | FY2023 ($M) | Change |\n"
                        "| --- | --- | --- | --- |\n"
                        "| iPhone | 201,183 | 200,583 | +0.3% |\n"
                        "| Mac | 29,984 | 29,357 | +2.1% |\n"
                        "| iPad | 26,694 | 28,300 | -5.7% |\n"
                        "| Services | 96,169 | 85,200 | +12.9% |\n"
                        "| Total Net Sales | 391,030 | 383,285 | +2.0% |"
                    ),
                },
            ],
        },
    ]

    generated = 0
    for filing in filings:
        meta_base = {
            "dataset": "edgar",
            "ticker": filing["ticker"],
            "company_name": filing["company_name"],
            "cik": filing["cik"],
            "form_type": filing["form_type"],
            "fiscal_year": filing["fiscal_year"],
            "fiscal_period": filing["fiscal_period"],
            "filing_date": filing["filing_date"],
            "accession_number": filing["accession_number"],
            "source_url": f"https://www.sec.gov/ix?doc=/Archives/edgar/data/{int(filing['cik'])}/{filing['accession_number'].replace('-', '')}/{filing['ticker'].lower()}-{filing['fiscal_year']}.htm",
        }

        for sec in filing["sections"]:
            if generated >= count:
                return

            doc_name = f"edgar/{filing['ticker']}/{filing['fiscal_year']}_{filing['form_type']}/{sec['item_id']}"
            sec_meta = {
                **meta_base,
                "section_id": sec["item_id"],
                "section_title": sec["title"],
                "hierarchy": {
                    "company": filing["company_name"],
                    "form": filing["form_type"],
                    "year": filing["fiscal_year"],
                    "section": sec["item_id"],
                },
            }

            yield create_trace_record(
                document_name=doc_name,
                content=f"# {filing['company_name']} - {sec['title']}\n\n{sec['text']}",
                source_uri=meta_base["source_url"],
                metadata=sec_meta,
                collection="edgar",
            )
            generated += 1


def fetch_sec_company_filings(
    cik: str,
    form_types: list[str] = ["10-K", "10-Q"],
    limit: int = 5,
    user_agent: str = DEFAULT_USER_AGENT,
) -> Generator[dict[str, Any], None, None]:
    """Fetch and segment SEC EDGAR filings for a given company CIK."""
    cik_padded = str(cik).zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    headers = {"User-Agent": user_agent, "Accept": "application/json"}

    req = urllib.request.Request(url, headers=headers)
    print(f"[EDGAR] Querying submissions for CIK {cik_padded}...")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[EDGAR Error] Failed to fetch CIK {cik_padded}: {e}")
        return

    company_name = data.get("name", "Unknown Company")
    ticker = (data.get("tickers") or ["SEC"])[0]
    recent = data.get("filings", {}).get("recent", {})

    forms = recent.get("form", [])
    accessions = recent.get("accessionNumber", [])
    filing_dates = recent.get("filingDate", [])
    primary_docs = recent.get("primaryDocument", [])
    report_dates = recent.get("reportDate", [])

    matched = 0
    for idx, form in enumerate(forms):
        if matched >= limit:
            break
        if form not in form_types:
            continue

        acc_num = accessions[idx]
        acc_no_hyphen = acc_num.replace("-", "")
        pdoc = primary_docs[idx]
        fdate = filing_dates[idx]
        rdate = report_dates[idx] if idx < len(report_dates) else fdate
        year = rdate[:4] if rdate else fdate[:4]

        doc_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_no_hyphen}/{pdoc}"
        print(f"[EDGAR] Fetching {form} for {ticker} ({acc_num})...")

        try:
            # SEC requires polite request pacing (max 10 req/sec)
            time.sleep(0.2)
            doc_req = urllib.request.Request(doc_url, headers=headers)
            with urllib.request.urlopen(doc_req, timeout=20) as doc_resp:
                raw_bytes = doc_resp.read()
                raw_html = raw_bytes.decode("utf-8", errors="replace")

            cleaned_text = clean_sec_html(raw_html)
            base_meta = {
                "dataset": "edgar",
                "ticker": ticker,
                "company_name": company_name,
                "cik": cik_padded,
                "form_type": form,
                "fiscal_year": year,
                "filing_date": fdate,
                "accession_number": acc_num,
                "source_url": doc_url,
            }

            for sec_rec in segment_filing_sections(cleaned_text, base_meta):
                yield sec_rec

            matched += 1
        except Exception as err:
            print(f"[EDGAR Error] Failed downloading document {doc_url}: {err}")
            continue


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch, segment, and stage SEC EDGAR 10-K & 10-Q corporate filings."
    )
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=DEFAULT_SCALE_DATA_ROOT / "edgar" / "sec_edgar_filings.jsonl",
        help=f"Destination JSONL filepath (default: {DEFAULT_SCALE_DATA_ROOT / 'edgar' / 'sec_edgar_filings.jsonl'})",
    )
    parser.add_argument(
        "--limit",
        "-n",
        type=int,
        default=None,
        help="Max number of filing sections to output.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run fast synthetic dry-run verification without SEC network requests.",
    )
    parser.add_argument(
        "--ciks",
        type=str,
        default="0001045810,0000320193,0000789019",  # NVDA, AAPL, MSFT
        help="Comma-separated list of CIK numbers or tickers to query.",
    )
    parser.add_argument(
        "--forms",
        type=str,
        default="10-K,10-Q",
        help="Comma-separated form types (e.g. 10-K,10-Q).",
    )
    parser.add_argument(
        "--user-agent",
        type=str,
        default=DEFAULT_USER_AGENT,
        help="SEC EDGAR compliant User-Agent header (must include admin contact email).",
    )

    args = parser.parse_args()

    print("=== SEC EDGAR Filings Ingestion & Staging Suite ===")
    get_default_staging_dir("edgar")

    if args.dry_run:
        print("[Mode] DRY-RUN verification")
        limit = args.limit or 10
        records = list(generate_synthetic_edgar_records(count=limit))
        count = write_jsonl_records(records, args.output, limit=limit)
        print(f"[Success] Dry-run staged {count} EDGAR filing sections to {args.output}")
        return 0

    cik_list = [c.strip() for c in args.ciks.split(",") if c.strip()]
    form_list = [f.strip() for f in args.forms.split(",") if f.strip()]

    def filing_stream() -> Generator[dict[str, Any], None, None]:
        for cik in cik_list:
            yield from fetch_sec_company_filings(
                cik=cik,
                form_types=form_list,
                limit=args.limit or 5,
                user_agent=args.user_agent,
            )

    count = write_jsonl_records(filing_stream(), args.output, limit=args.limit)
    print(f"[Done] Staged {count:,} EDGAR records to {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
