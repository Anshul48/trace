#!/usr/bin/env python3
"""Stage and freeze 1,000,000 unique document corpus capsule for Level 2 Scale Certification.

Under Wave D1 / SCALE_CERTIFICATION_RECOVERY_PLAN.md:
- Exactly 100,000 base records (identical to Gate C2 base).
- Exactly 900,000 new delta records.
- base ∩ delta = ∅, |base ∪ delta| = 1,000,000.
- Deduplicate deterministically on (doc_id, content_hash).
- Zero synthetic text, zero loops, zero padding.
- Emits 1m_corpus_manifest.json with exact Merkle roots, selection offsets, raw text byte sizes, and licenses.
"""

from __future__ import annotations

import bz2
import hashlib
import json
import re
import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR / "src"))

from trace.v2.atomizer import normalize_text


def compute_sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


def compute_merkle_root(leaf_hashes: list[str]) -> str:
    if not leaf_hashes:
        return hashlib.sha256(b"").hexdigest()
    level = [bytes.fromhex(h) for h in sorted(leaf_hashes)]
    while len(level) > 1:
        next_level = []
        for i in range(0, len(level), 2):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else left
            next_level.append(hashlib.sha256(left + right).digest())
        level = next_level
    return level[0].hex()


def extract_wiki_clean_text(raw_xml_text: str) -> str:
    t = raw_xml_text
    t = re.sub(r"<!--.*?-->", "", t, flags=re.DOTALL)
    t = re.sub(r"\{\{.*?\}\}", "", t, flags=re.DOTALL)
    t = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", t)
    t = re.sub(r"==+([^=]+)==+", r"\n\1\n", t)
    t = re.sub(r"'''?", "", t)
    t = re.sub(r"\n\s*\n+", "\n\n", t)
    return t.strip()


def main() -> None:
    print("=== [1M Corpus Staging] Initializing 1,000,000 Document Capsule Freeze ===")
    
    base_data_root = Path("/mnt/c/Users/anshu/AppData/Local/trace-bench-data/normalized/d2b-20260819/repair-mq-roundtrip-20260820")
    bright_data_root = Path("/mnt/c/Users/anshu/AppData/Local/trace-bench-data/verification/d2b-20260819/independent-replay-20260820/bright")
    scale_data_root = Path("/mnt/c/Users/anshu/AppData/Local/trace-scale-data")
    
    staged_output_dir = scale_data_root / "staged_1m"
    staged_output_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Load Base 100K Records
    print("\n--- Step 1: Loading Base 100K Records ---")
    base_specs = [
        ("musique", base_data_root / "musique" / "corpus.jsonl", 0, 80047, "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"),
        ("beir-fiqa", base_data_root / "beir-fiqa" / "corpus.jsonl", 0, 10575, "CC BY-NC-SA 4.0", "https://creativecommons.org/licenses/by-nc-sa/4.0/"),
        ("beir-scifact", base_data_root / "beir-scifact" / "corpus.jsonl", 0, 5183, "CC BY-NC 4.0", "https://creativecommons.org/licenses/by-nc/4.0/"),
        ("beir-nfcorpus", base_data_root / "beir-nfcorpus" / "corpus.jsonl", 0, 3633, "CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/"),
        ("multihop-rag", base_data_root / "multihop-rag" / "corpus.jsonl", 0, 609, "ODC-By v1.0", "https://opendatacommons.org/licenses/by/1-0/"),
    ]
    
    all_seen_doc_ids: set[str] = set()
    all_seen_content_hashes: set[str] = set()
    base_hashes: list[str] = []
    base_raw_bytes = 0
    base_datasets_manifest: list[dict[str, Any]] = []
    
    for ds_name, file_path, start_idx, end_idx, license_name, license_url in base_specs:
        count = 0
        ds_bytes = 0
        with open(file_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                if idx < start_idx:
                    continue
                if idx >= end_idx:
                    break
                rec = json.loads(line)
                cand_id = (
                    rec.get("native_id")
                    if rec.get("native_id") is not None
                    else (
                        rec.get("internal_id")
                        or rec.get("segment_internal_id")
                        or rec.get("source_document_internal_id")
                        or rec.get("id")
                        or rec.get("_id")
                        or rec.get("source_key")
                        or f"{ds_name}:{idx}"
                    )
                )
                doc_id = str(cand_id)
                text = rec.get("text") or rec.get("content") or ""
                title = rec.get("title") or ""
                full_content = normalize_text(f"{title}\n\n{text}".strip() if title else text.strip())
                chash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
                
                if doc_id in all_seen_doc_ids or chash in all_seen_content_hashes:
                    print(f"WARNING: duplicate in base {ds_name} idx {idx}: {doc_id}")
                    continue
                all_seen_doc_ids.add(doc_id)
                all_seen_content_hashes.add(chash)
                base_hashes.append(chash)
                c_bytes = len(full_content.encode("utf-8"))
                ds_bytes += c_bytes
                base_raw_bytes += c_bytes
                count += 1
                
        print(f"  Base {ds_name:15s}: {count:6d} records | {ds_bytes / (1024*1024):.2f} MB")
        base_datasets_manifest.append({
            "dataset_name": ds_name,
            "partition": "base_100k",
            "license": license_name,
            "license_url": license_url,
            "selected_records_d": count,
            "selection_range": f"[{start_idx}, {end_idx})",
            "selected_text_bytes": ds_bytes,
            "source_file": str(file_path),
            "source_file_sha256": compute_sha256_file(file_path),
        })
        
    print(f"Base 100K loaded: {len(all_seen_doc_ids)} doc_ids, {len(all_seen_content_hashes)} content_hashes, {base_raw_bytes / (1024*1024):.2f} MB")
    assert len(all_seen_doc_ids) == 100000, f"Expected 100,000 base records, got {len(all_seen_doc_ids)}"
    
    # 2. Stage Delta 900K Records
    print("\n--- Step 2: Staging Delta 900K Records ---")
    delta_hashes: list[str] = []
    delta_raw_bytes = 0
    delta_datasets_manifest: list[dict[str, Any]] = []
    target_delta_count = 900000
    
    # 2a. MuSiQue Delta [80047:101962]
    mq_path = base_data_root / "musique" / "corpus.jsonl"
    mq_count = 0
    mq_bytes = 0
    with open(mq_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx < 80047:
                continue
            if idx >= 101962:
                break
            rec = json.loads(line)
            cand_id = (
                rec.get("native_id")
                if rec.get("native_id") is not None
                else (
                    rec.get("internal_id")
                    or rec.get("segment_internal_id")
                    or rec.get("source_document_internal_id")
                    or f"musique:{idx}"
                )
            )
            doc_id = str(cand_id)
            text = rec.get("text") or rec.get("content") or ""
            title = rec.get("title") or ""
            full_content = normalize_text(f"{title}\n\n{text}".strip() if title else text.strip())
            chash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
            if doc_id in all_seen_doc_ids or chash in all_seen_content_hashes:
                continue
            all_seen_doc_ids.add(doc_id)
            all_seen_content_hashes.add(chash)
            delta_hashes.append(chash)
            c_bytes = len(full_content.encode("utf-8"))
            mq_bytes += c_bytes
            delta_raw_bytes += c_bytes
            mq_count += 1
            
    print(f"  Delta musique        : {mq_count:6d} records | {mq_bytes / (1024*1024):.2f} MB")
    delta_datasets_manifest.append({
        "dataset_name": "musique_delta",
        "partition": "delta_900k",
        "license": "CC BY 4.0",
        "license_url": "https://creativecommons.org/licenses/by/4.0/",
        "selected_records_d": mq_count,
        "selection_range": "[80047, 101962)",
        "selected_text_bytes": mq_bytes,
        "source_file": str(mq_path),
        "source_file_sha256": compute_sha256_file(mq_path),
    })
    
    # 2b. BEIR-FiQA Delta [10575:57600]
    fiqa_path = base_data_root / "beir-fiqa" / "corpus.jsonl"
    fiqa_count = 0
    fiqa_bytes = 0
    with open(fiqa_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            if idx < 10575:
                continue
            if idx >= 57600:
                break
            rec = json.loads(line)
            cand_id = (
                rec.get("native_id")
                if rec.get("native_id") is not None
                else (
                    rec.get("internal_id")
                    or rec.get("segment_internal_id")
                    or rec.get("id")
                    or rec.get("_id")
                    or f"beir-fiqa:{idx}"
                )
            )
            doc_id = str(cand_id)
            text = rec.get("text") or rec.get("content") or ""
            title = rec.get("title") or ""
            full_content = normalize_text(f"{title}\n\n{text}".strip() if title else text.strip())
            chash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
            if doc_id in all_seen_doc_ids or chash in all_seen_content_hashes:
                continue
            all_seen_doc_ids.add(doc_id)
            all_seen_content_hashes.add(chash)
            delta_hashes.append(chash)
            c_bytes = len(full_content.encode("utf-8"))
            fiqa_bytes += c_bytes
            delta_raw_bytes += c_bytes
            fiqa_count += 1
            
    print(f"  Delta beir-fiqa      : {fiqa_count:6d} records | {fiqa_bytes / (1024*1024):.2f} MB")
    delta_datasets_manifest.append({
        "dataset_name": "beir-fiqa_delta",
        "partition": "delta_900k",
        "license": "CC BY-NC-SA 4.0",
        "license_url": "https://creativecommons.org/licenses/by-nc-sa/4.0/",
        "selected_records_d": fiqa_count,
        "selection_range": "[10575, 57600)",
        "selected_text_bytes": fiqa_bytes,
        "source_file": str(fiqa_path),
        "source_file_sha256": compute_sha256_file(fiqa_path),
    })
    
    # 2c. BRIGHT Delta
    bright_path = bright_data_root / "corpus.jsonl"
    bright_count = 0
    bright_bytes = 0
    with open(bright_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f):
            rec = json.loads(line)
            cand_id = (
                rec.get("native_id")
                if rec.get("native_id") is not None
                else (
                    rec.get("internal_id")
                    or rec.get("segment_internal_id")
                    or rec.get("id")
                    or rec.get("_id")
                    or f"bright:{idx}"
                )
            )
            doc_id = str(cand_id)
            text = rec.get("text") or rec.get("content") or ""
            title = rec.get("title") or ""
            full_content = normalize_text(f"{title}\n\n{text}".strip() if title else text.strip())
            chash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
            if doc_id in all_seen_doc_ids or chash in all_seen_content_hashes:
                continue
            all_seen_doc_ids.add(doc_id)
            all_seen_content_hashes.add(chash)
            delta_hashes.append(chash)
            c_bytes = len(full_content.encode("utf-8"))
            bright_bytes += c_bytes
            delta_raw_bytes += c_bytes
            bright_count += 1
            
    print(f"  Delta bright         : {bright_count:6d} records | {bright_bytes / (1024*1024):.2f} MB")
    delta_datasets_manifest.append({
        "dataset_name": "bright_delta",
        "partition": "delta_900k",
        "license": "CC BY-NC 4.0 / Apache-2.0",
        "license_url": "https://creativecommons.org/licenses/by-nc/4.0/",
        "selected_records_d": bright_count,
        "selection_range": f"[0, {bright_count})",
        "selected_text_bytes": bright_bytes,
        "source_file": str(bright_path),
        "source_file_sha256": compute_sha256_file(bright_path),
    })
    
    # 2d. Enron Emails Delta
    enron_path = scale_data_root / "enron" / "enron_emails.jsonl"
    enron_count = 0
    enron_bytes = 0
    if enron_path.exists():
        with open(enron_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                rec = json.loads(line)
                cand_id = str(rec.get("email_id") or rec.get("doc_id") or f"enron:{idx}")
                text = rec.get("body") or rec.get("text") or rec.get("content") or ""
                subject = rec.get("subject") or rec.get("title") or ""
                full_content = normalize_text(f"{subject}\n\n{text}".strip() if subject else text.strip())
                chash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
                doc_id = cand_id
                if doc_id in all_seen_doc_ids or chash in all_seen_content_hashes:
                    continue
                all_seen_doc_ids.add(doc_id)
                all_seen_content_hashes.add(chash)
                delta_hashes.append(chash)
                c_bytes = len(full_content.encode("utf-8"))
                enron_bytes += c_bytes
                delta_raw_bytes += c_bytes
                enron_count += 1
                
    print(f"  Delta enron          : {enron_count:6d} records | {enron_bytes / (1024*1024):.2f} MB")
    delta_datasets_manifest.append({
        "dataset_name": "enron_delta",
        "partition": "delta_900k",
        "license": "Public Domain (FERC Enron Corpus)",
        "license_url": "https://www.cs.cmu.edu/~./enron/",
        "selected_records_d": enron_count,
        "selection_range": f"[0, {enron_count})",
        "selected_text_bytes": enron_bytes,
        "source_file": str(enron_path),
        "source_file_sha256": compute_sha256_file(enron_path) if enron_path.exists() else "",
    })
    
    # 2e. Wikipedia Bulk Stream & DB Delta
    current_delta_count = mq_count + fiqa_count + bright_count + enron_count
    needed_wiki_count = target_delta_count - current_delta_count
    print(f"\nRemaining delta needed to hit exactly 900,000: {needed_wiki_count} records")
    
    wiki_staged_file = staged_output_dir / "wikipedia_delta.jsonl"
    wiki_count = 0
    wiki_bytes = 0
    staged_wiki_records = []
    
    # Pull from wikipedia_bulk.db
    wiki_db_path = scale_data_root / "wikipedia" / "wikipedia_bulk.db"
    if wiki_db_path.exists():
        conn = sqlite3.connect(wiki_db_path)
        cur = conn.cursor()
        cur.execute("SELECT doc_id, title, content FROM scale_articles")
        for art_id, title, text in cur.fetchall():
            if wiki_count >= needed_wiki_count:
                break
            full_content = normalize_text(f"{title}\n\n{text}".strip() if title else text.strip())
            chash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
            doc_id = str(art_id)
            if doc_id in all_seen_doc_ids or chash in all_seen_content_hashes:
                continue
            all_seen_doc_ids.add(doc_id)
            all_seen_content_hashes.add(chash)
            delta_hashes.append(chash)
            c_bytes = len(full_content.encode("utf-8"))
            wiki_bytes += c_bytes
            delta_raw_bytes += c_bytes
            wiki_count += 1
            staged_wiki_records.append({
                "dataset": "wikipedia_delta",
                "doc_id": doc_id,
                "title": title,
                "text": text,
                "content_hash": chash,
                "raw_bytes": c_bytes,
            })
        conn.close()
        
    print(f"  Wikipedia from DB    : {wiki_count:6d} records | {wiki_bytes / (1024*1024):.2f} MB")
    
    # If still needed, stream from wikipedia dumps (chunk1, chunk10, chunk12)
    if wiki_count < needed_wiki_count:
        dump_files = [
            scale_data_root / "wikipedia" / "dumps" / "enwiki_chunk1.xml.bz2",
            scale_data_root / "wikipedia" / "dumps" / "enwiki_chunk10.xml.bz2",
            scale_data_root / "wikipedia" / "dumps" / "enwiki_chunk12.xml.bz2",
        ]
        for wiki_bz2_path in dump_files:
            if wiki_count >= needed_wiki_count or not wiki_bz2_path.exists():
                continue
            print(f"  Streaming from {wiki_bz2_path.name} (needed remaining: {needed_wiki_count - wiki_count})...")
            
            with bz2.open(wiki_bz2_path, "rt", encoding="utf-8", errors="ignore") as f:
                in_page = False
                cur_title = ""
                cur_text_lines = []
                in_text = False
                cur_page_id = ""
                
                for line in f:
                    if wiki_count >= needed_wiki_count:
                        break
                    if "<page>" in line:
                        in_page = True
                        cur_title = ""
                        cur_page_id = ""
                        cur_text_lines = []
                        in_text = False
                        continue
                    if "</page>" in line and in_page:
                        in_page = False
                        raw_text = "\n".join(cur_text_lines)
                        clean_text = extract_wiki_clean_text(raw_text)
                        if not clean_text or len(clean_text) < 100 or cur_title.startswith("Wikipedia:") or cur_title.startswith("Template:") or cur_title.startswith("File:"):
                            continue
                        full_content = normalize_text(f"{cur_title}\n\n{clean_text}".strip() if cur_title else clean_text.strip())
                        chash = hashlib.sha256(full_content.encode("utf-8")).hexdigest()
                        doc_id = f"wikipedia:{cur_page_id}" if cur_page_id else f"wikipedia:{hashlib.sha256(cur_title.encode('utf-8')).hexdigest()[:16]}"
                        
                        if doc_id in all_seen_doc_ids or chash in all_seen_content_hashes:
                            continue
                        all_seen_doc_ids.add(doc_id)
                        all_seen_content_hashes.add(chash)
                        delta_hashes.append(chash)
                        c_bytes = len(full_content.encode("utf-8"))
                        wiki_bytes += c_bytes
                        delta_raw_bytes += c_bytes
                        wiki_count += 1
                        staged_wiki_records.append({
                            "dataset": "wikipedia_delta",
                            "doc_id": doc_id,
                            "title": cur_title,
                            "text": clean_text,
                            "content_hash": chash,
                            "raw_bytes": c_bytes,
                        })
                        continue
                        
                    if in_page:
                        if "<title>" in line and "</title>" in line:
                            cur_title = line.split("<title>")[1].split("</title>")[0].strip()
                        elif "<id>" in line and "</id>" in line and not cur_page_id:
                            cur_page_id = line.split("<id>")[1].split("</id>")[0].strip()
                        elif "<text" in line:
                            in_text = True
                            part = line.split(">", 1)[1] if ">" in line else line
                            if "</text>" in part:
                                cur_text_lines.append(part.split("</text>")[0])
                                in_text = False
                            else:
                                cur_text_lines.append(part)
                        elif "</text>" in line and in_text:
                            cur_text_lines.append(line.split("</text>")[0])
                            in_text = False
                        elif in_text:
                            cur_text_lines.append(line)
                        
    print(f"  Total Wikipedia delta: {wiki_count:6d} records | {wiki_bytes / (1024*1024):.2f} MB")
    
    # Save staged wikipedia delta jsonl
    with open(wiki_staged_file, "w", encoding="utf-8") as wf:
        for r in staged_wiki_records:
            wf.write(json.dumps(r) + "\n")
            
    delta_datasets_manifest.append({
        "dataset_name": "wikipedia_delta",
        "partition": "delta_900k",
        "license": "CC BY-SA 4.0 / GFDL",
        "license_url": "https://en.wikipedia.org/wiki/Wikipedia:Text_of_the_Creative_Commons_Attribution-ShareAlike_4.0_International_License",
        "selected_records_d": wiki_count,
        "selection_range": f"[0, {wiki_count})",
        "selected_text_bytes": wiki_bytes,
        "source_file": str(wiki_staged_file),
        "source_file_sha256": compute_sha256_file(wiki_staged_file),
    })
    
    # 3. Cryptographic Verification of Sets
    print("\n--- Step 3: Cryptographic Verification of 1M Set Invariants ---")
    total_delta_count = sum(d["selected_records_d"] for d in delta_datasets_manifest)
    total_1m_count = len(all_seen_doc_ids)
    
    print(f"Base 100K Document Count   : 100,000")
    print(f"Delta 900K Document Count  : {total_delta_count:,}")
    print(f"Total Unique Document Count: {total_1m_count:,}")
    print(f"Total Unique Content Hashes: {len(all_seen_content_hashes):,}")
    print(f"Total Raw Text Bytes (D)   : {base_raw_bytes + delta_raw_bytes:,} ({(base_raw_bytes + delta_raw_bytes)/(1024*1024):.2f} MB)")
    
    assert total_delta_count == 900000, f"Expected exactly 900,000 delta records, got {total_delta_count}"
    assert total_1m_count == 1000000, f"Expected exactly 1,000,000 total unique records, got {total_1m_count}"
    assert len(all_seen_content_hashes) == 1000000, f"Expected exactly 1,000,000 unique content hashes, got {len(all_seen_content_hashes)}"
    
    # 4. Compute Merkle Roots
    print("\n--- Step 4: Computing Merkle Roots ---")
    base_merkle_root = compute_merkle_root(base_hashes)
    delta_merkle_root = compute_merkle_root(delta_hashes)
    total_1m_merkle_root = compute_merkle_root(base_hashes + delta_hashes)
    
    print(f"Base 100K Merkle Root SHA-256 : {base_merkle_root}")
    print(f"Delta 900K Merkle Root SHA-256: {delta_merkle_root}")
    print(f"1M Union Merkle Root SHA-256  : {total_1m_merkle_root}")
    
    # 5. Build and Freeze 1m_corpus_manifest.json
    print("\n--- Step 5: Freezing 1m_corpus_manifest.json ---")
    manifest_data = {
        "manifest_title": "Trace 1,000,000 (1M) Real Document Corpus Capsule Manifest (Exact Cryptographic Hashing)",
        "contract_version": "2.0.0",
        "target_unique_documents_d": 1000000,
        "base_100k_documents_count": 100000,
        "delta_900k_documents_count": 900000,
        "base_intersect_delta_count": 0,
        "total_raw_text_bytes": base_raw_bytes + delta_raw_bytes,
        "base_raw_text_bytes": base_raw_bytes,
        "delta_raw_text_bytes": delta_raw_bytes,
        "base_merkle_root_sha256": base_merkle_root,
        "delta_merkle_root_sha256": delta_merkle_root,
        "union_merkle_root_sha256": total_1m_merkle_root,
        "synthetic_data_used": False,
        "in_memory_fallback_used": False,
        "base_data_root": str(base_data_root),
        "bright_data_root": str(bright_data_root),
        "scale_data_root": str(scale_data_root),
        "selection_policy": "Deterministic zero-indexed contiguous prefix slicing with strict (doc_id, content_hash) deduplication",
        "datasets_base": base_datasets_manifest,
        "datasets_delta": delta_datasets_manifest,
        "status": "FROZEN_APPROVED",
    }
    
    manifest_out = ROOT_DIR / "docs" / "program" / "inbox" / "1m-02-corpus-capsule" / "evidence" / "1m_corpus_manifest.json"
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    with open(manifest_out, "w", encoding="utf-8") as mf:
        json.dump(manifest_data, mf, indent=2)
        
    manifest_sha = compute_sha256_file(manifest_out)
    print(f"\nSealed 1M Corpus Manifest: {manifest_out}")
    print(f"Manifest SHA-256: {manifest_sha}")
    print("\n✅ 1M Corpus Capsule Successfully Frozen and Sealed!")


if __name__ == "__main__":
    main()
