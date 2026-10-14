"""High-Performance GPU-Accelerated Baseline Runner (NVIDIA RTX 5050 SM120)"""
import os
import sys
import json
import time
import math
import re
import struct
import tracemalloc
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
import numpy as np
import torch
from transformers import AutoTokenizer, AutoModel

tracemalloc.start()

sys.path.insert(0, r"C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench\src")
import trace_bench
from trace_bench.metrics.retrieval import evaluate_case_retrieval

DATA_ROOT = Path(r"C:\Users\anshu\AppData\Local\trace-bench-data\normalized\d2b-20260819\repair-mq-roundtrip-20260820")
RAW_SIFT_ROOT = Path(r"C:\Users\anshu\AppData\Local\trace-bench-data\bigann\raw\sift")
RUNS_DIR = Path(r"C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\inbox\s6-baselines-p005-20260825\evidence\runs")
EVIDENCE_DIR = Path(r"C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\inbox\s6-baselines-p005-20260825\evidence")

RUNS_DIR.mkdir(parents=True, exist_ok=True)

DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Executing on Device: {DEVICE} ({torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'})", flush=True)

def get_current_rss_mb() -> float:
    try:
        current, peak = tracemalloc.get_traced_memory()
        return float(peak / (1024 * 1024))
    except Exception:
        return 0.0

def tokenize(text: str) -> list[str]:
    return re.findall(r"\b[a-zA-Z0-9_]+\b", text.lower())

def extract_entities(text: str) -> list[str]:
    phrases = re.findall(r"\b[A-Z][a-zA-Z0-9_-]*(?:\s+[A-Z][a-zA-Z0-9_-]*)*\b", text)
    tokens = re.findall(r"\b[a-zA-Z0-9_]{3,}\b", text.lower())
    return [p.lower() for p in phrases] + tokens

# Fast Vectorized Inverted Index BM25
class VectorizedBM25:
    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b
        self.num_docs = 0
        self.avg_doc_len = 0.0
        self.doc_len_ratio = None
        self.idf = {}
        self.postings_docs = {}
        self.postings_tfs = {}

    def index(self, documents: list[dict]):
        self.num_docs = len(documents)
        if self.num_docs == 0:
            return
        doc_lens = np.empty(self.num_docs, dtype=np.float32)
        raw_postings = defaultdict(lambda: ([], []))
        doc_freqs = Counter()

        for idx, doc in enumerate(documents):
            text = ((doc.get("title") or "") + " " + (doc.get("text") or "")).strip()
            tokens = tokenize(text)
            t_len = len(tokens)
            doc_lens[idx] = t_len
            counts = Counter(tokens)
            for term, tf in counts.items():
                raw_postings[term][0].append(idx)
                raw_postings[term][1].append(tf)
                doc_freqs[term] += 1

        self.avg_doc_len = float(np.mean(doc_lens)) if self.num_docs > 0 else 1.0
        self.doc_len_ratio = (doc_lens / self.avg_doc_len).astype(np.float32)

        self.idf = {}
        self.postings_docs = {}
        self.postings_tfs = {}
        for term, df in doc_freqs.items():
            self.idf[term] = float(math.log(1.0 + (self.num_docs - df + 0.5) / (df + 0.5)))
            self.postings_docs[term] = np.array(raw_postings[term][0], dtype=np.int32)
            self.postings_tfs[term] = np.array(raw_postings[term][1], dtype=np.float32)

    def retrieve_single(self, query: str, top_k: int = 50) -> list[tuple[int, float]]:
        tokens = tokenize(query)
        if not tokens or self.num_docs == 0:
            return []
        scores = np.zeros(self.num_docs, dtype=np.float32)
        has_score = False

        for term in set(tokens):
            if term not in self.idf:
                continue
            idf_val = self.idf[term]
            docs = self.postings_docs[term]
            tfs = self.postings_tfs[term]
            len_ratios = self.doc_len_ratio[docs]
            term_scores = idf_val * (tfs * (self.k1 + 1.0)) / (tfs + self.k1 * (1.0 - self.b + self.b * len_ratios))
            scores[docs] += term_scores
            has_score = True

        if not has_score:
            return []

        if self.num_docs <= top_k:
            top_indices = np.argsort(-scores)
        else:
            cand_indices = np.argpartition(-scores, top_k)[:top_k]
            sorted_cand_indices = np.argsort(-scores[cand_indices])
            top_indices = cand_indices[sorted_cand_indices]

        results = []
        for idx in top_indices:
            sc = float(scores[idx])
            if sc > 0:
                results.append((int(idx), sc))
        return results

# GPU-Accelerated Dense Retriever
class GPUDenseRetriever:
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", device: str = DEVICE):
        self.model_name = model_name
        self.device = device
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model = AutoModel.from_pretrained(model_name).to(self.device)
        self.model.eval()
        self.doc_embeddings_gpu = None
        self.num_docs = 0

    def _mean_pooling(self, model_output, attention_mask):
        token_embeddings = model_output[0]
        input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
        return torch.sum(token_embeddings * input_mask_expanded, 1) / torch.clamp(input_mask_expanded.sum(1), min=1e-9)

    def encode_texts(self, texts: list[str], batch_size: int = 512, max_length: int = 128) -> torch.Tensor:
        all_embs = []
        with torch.no_grad():
            for i in range(0, len(texts), batch_size):
                batch_texts = texts[i:i + batch_size]
                encoded = self.tokenizer(
                    batch_texts,
                    padding=True,
                    truncation=True,
                    max_length=max_length,
                    return_tensors="pt"
                ).to(self.device)
                out = self.model(**encoded)
                embs = self._mean_pooling(out, encoded["attention_mask"])
                embs = torch.nn.functional.normalize(embs, p=2, dim=1)
                all_embs.append(embs)
        return torch.cat(all_embs, dim=0)

    def index(self, documents: list[dict], batch_size: int = 512):
        self.num_docs = len(documents)
        if self.num_docs == 0:
            self.doc_embeddings_gpu = None
            return
        texts = [((d.get("title") or "") + " " + (d.get("text") or "")).strip() for d in documents]
        self.doc_embeddings_gpu = self.encode_texts(texts, batch_size=batch_size)

    def retrieve_batch(self, query_texts: list[str], top_k: int = 50, batch_size: int = 512) -> tuple[list[list[tuple[int, float]]], float]:
        t0 = time.perf_counter()
        q_embs = self.encode_texts(query_texts, batch_size=batch_size)
        sims = torch.mm(q_embs, self.doc_embeddings_gpu.T) # shape: (Q, N)
        k_val = min(top_k, self.num_docs)
        top_vals, top_indices = torch.topk(sims, k=k_val, dim=1)
        torch.cuda.synchronize() if self.device == "cuda" else None
        total_time = time.perf_counter() - t0

        top_indices_cpu = top_indices.cpu().numpy()
        top_vals_cpu = top_vals.cpu().numpy()

        results = []
        for q_idx in range(len(query_texts)):
            row_idx = top_indices_cpu[q_idx]
            row_vals = top_vals_cpu[q_idx]
            results.append([(int(doc_i), float(val)) for doc_i, val in zip(row_idx, row_vals)])
        return results, total_time

# SIFT Vector Ops
def read_fvecs(filename: str, max_vectors: int = None) -> np.ndarray:
    with open(filename, "rb") as f:
        dim_bytes = f.read(4)
        if not dim_bytes:
            return np.empty((0, 0), dtype=np.float32)
        dim = struct.unpack("i", dim_bytes)[0]
        f.seek(0)
        row_size = 4 + dim * 4
        f.seek(0, os.SEEK_END)
        total_size = f.tell()
        n_vectors = total_size // row_size
        if max_vectors is not None:
            n_vectors = min(n_vectors, max_vectors)
        f.seek(0)
        data = np.empty((n_vectors, dim), dtype=np.float32)
        for i in range(n_vectors):
            f.read(4)
            raw = f.read(dim * 4)
            data[i] = struct.unpack(f"{dim}f", raw)
    return data

def read_ivecs(filename: str, max_vectors: int = None) -> np.ndarray:
    with open(filename, "rb") as f:
        dim_bytes = f.read(4)
        if not dim_bytes:
            return np.empty((0, 0), dtype=np.int32)
        dim = struct.unpack("i", dim_bytes)[0]
        f.seek(0)
        row_size = 4 + dim * 4
        f.seek(0, os.SEEK_END)
        total_size = f.tell()
        n_vectors = total_size // row_size
        if max_vectors is not None:
            n_vectors = min(n_vectors, max_vectors)
        f.seek(0)
        data = np.empty((n_vectors, dim), dtype=np.int32)
        for i in range(n_vectors):
            f.read(4)
            raw = f.read(dim * 4)
            data[i] = struct.unpack(f"{dim}i", raw)
    return data

def load_dataset(dataset_name: str):
    d_dir = DATA_ROOT / dataset_name
    corpus_file = d_dir / "corpus.jsonl"
    manifest_file = d_dir / "manifest.json"

    with open(corpus_file, "r", encoding="utf-8") as f:
        corpus_docs = [json.loads(line) for line in f]
    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    key_to_atom = {}
    for idx, d in enumerate(corpus_docs):
        atom_id = f"atom-{idx}"
        if d.get("native_id"):
            key_to_atom[str(d["native_id"])] = atom_id
        if d.get("source_key"):
            key_to_atom[str(d["source_key"])] = atom_id
            key_to_atom["derived:source-" + str(d["source_key"])] = atom_id
        if d.get("internal_id"):
            key_to_atom[str(d["internal_id"])] = atom_id
            key_to_atom["derived:segment:" + str(d["internal_id"])] = atom_id
            key_to_atom[f"derived:source-row:{idx+1}"] = atom_id

    resolved_cases = []
    for c in manifest["cases"]:
        golds = c.get("native_gold_doc_ids", [])
        gold_atoms = [key_to_atom[str(g)] for g in golds if str(g) in key_to_atom]
        c_copy = dict(c)
        c_copy["gold_atom_ids"] = gold_atoms
        resolved_cases.append(c_copy)

    return corpus_docs, resolved_cases, manifest

def compute_aggregate_metrics(case_records: list[dict], latencies: list[float], index_time: float, n_docs: int, peak_mem: float) -> dict:
    total_q = len(case_records)
    pos_cases = [c for c in case_records if not c["expected_abstention"]]
    abs_cases = [c for c in case_records if c["expected_abstention"]]
    
    n_pos = len(pos_cases)
    n_abs = len(abs_cases)

    rec5 = float(np.mean([c["recall_at_5"] for c in pos_cases])) if n_pos else 0.0
    rec20 = float(np.mean([c["recall_at_20"] for c in pos_cases])) if n_pos else 0.0
    rec100 = float(np.mean([c["recall_at_100"] for c in pos_cases])) if n_pos else 0.0
    ndcg10 = float(np.mean([c["ndcg_at_10"] for c in pos_cases])) if n_pos else 0.0
    ndcg30 = float(np.mean([c["ndcg_at_30"] for c in pos_cases])) if n_pos else 0.0
    cov10 = float(np.mean([c["complete_gold_coverage_at_10"] for c in pos_cases])) if n_pos else 0.0
    cov20 = float(np.mean([c["complete_gold_coverage_at_20"] for c in pos_cases])) if n_pos else 0.0
    prec5 = float(np.mean([c["citation_precision_at_5"] for c in pos_cases])) if n_pos else 0.0
    prec10 = float(np.mean([c["citation_precision_at_10"] for c in pos_cases])) if n_pos else 0.0
    mrr = float(np.mean([c["mrr"] for c in pos_cases])) if n_pos else 0.0
    mhop_cov = float(np.mean([c["multihop_coverage"] for c in pos_cases])) if n_pos else 0.0

    abs_acc = float(np.mean([c["abstention_accuracy"] for c in case_records])) if total_q else 0.0

    lat_arr = np.array(latencies) * 1000.0
    total_wall_sec = sum(latencies)
    qps = total_q / total_wall_sec if total_wall_sec > 0 else 0.0

    outcome_counts = Counter(c["outcome"] for c in case_records)

    return {
        "total_cases": total_q,
        "positive_cases_count": n_pos,
        "expected_abstention_count": n_abs,
        "outcomes": dict(outcome_counts),
        "metrics": {
            "recall_at_5": rec5,
            "recall_at_20": rec20,
            "recall_at_100": rec100,
            "ndcg_at_10": ndcg10,
            "ndcg_at_30": ndcg30,
            "complete_gold_coverage_at_10": cov10,
            "complete_gold_coverage_at_20": cov20,
            "citation_precision_at_5": prec5,
            "citation_precision_at_10": prec10,
            "mrr": mrr,
            "multihop_coverage": mhop_cov,
            "abstention_accuracy": abs_acc,
        },
        "ops": {
            "latency_p50_ms": float(np.percentile(lat_arr, 50)) if len(lat_arr) else 0.0,
            "latency_p90_ms": float(np.percentile(lat_arr, 90)) if len(lat_arr) else 0.0,
            "latency_p95_ms": float(np.percentile(lat_arr, 95)) if len(lat_arr) else 0.0,
            "latency_p99_ms": float(np.percentile(lat_arr, 99)) if len(lat_arr) else 0.0,
            "latency_mean_ms": float(np.mean(lat_arr)) if len(lat_arr) else 0.0,
            "latency_min_ms": float(np.min(lat_arr)) if len(lat_arr) else 0.0,
            "latency_max_ms": float(np.max(lat_arr)) if len(lat_arr) else 0.0,
            "latency_std_ms": float(np.std(lat_arr)) if len(lat_arr) else 0.0,
            "concurrent_qps": qps,
            "ingestion_duration_sec": index_time,
            "ingestion_docs_per_sec": n_docs / index_time if index_time > 0 else 0.0,
            "peak_memory_rss_mb": peak_mem,
        }
    }

def evaluate_dataset_suite(name: str, has_dense: bool = True, has_hipporag: bool = False, dense_retriever: GPUDenseRetriever = None):
    print(f"\n========================================================================", flush=True)
    print(f"Evaluating Dataset: {name}", flush=True)
    print(f"========================================================================", flush=True)
    corpus_docs, cases, manifest = load_dataset(name)
    n_docs = len(corpus_docs)
    n_cases = len(cases)
    print(f"  Loaded {n_cases} cases and {n_docs} corpus documents.", flush=True)

    ds_res = {}

    # 1. BM25 Lexical
    bm25 = VectorizedBM25()
    t0 = time.perf_counter()
    bm25.index(corpus_docs)
    bm25_idx_time = time.perf_counter() - t0
    print(f"  [BM25] Indexed {n_docs} docs in {bm25_idx_time:.3f}s ({n_docs/bm25_idx_time:.1f} docs/sec)", flush=True)

    bm25_retrieved_list = []
    bm25_cases = []
    bm25_lats = []
    t_start_all = time.perf_counter()
    for c in cases:
        t_start = time.perf_counter()
        cands = bm25.retrieve_single(c["query"], top_k=50)
        lat = time.perf_counter() - t_start
        bm25_lats.append(lat)
        retrieved_ids = [f"atom-{idx}" for idx, _ in cands]
        bm25_retrieved_list.append(cands)
        m = evaluate_case_retrieval(c["id"], c["category"], retrieved_ids, c["gold_atom_ids"], False, c["expected_abstention"])
        bm25_cases.append({
            "case_id": c["id"], "native_query_id": c.get("native_query_id"), "category": c["category"],
            "expected_abstention": c["expected_abstention"], "recall_at_5": m.recall_at_5, "recall_at_20": m.recall_at_20,
            "recall_at_100": m.recall_at_100, "ndcg_at_10": m.ndcg_at_10, "ndcg_at_30": m.ndcg_at_30,
            "complete_gold_coverage_at_10": m.complete_gold_coverage_at_10, "complete_gold_coverage_at_20": m.complete_gold_coverage_at_20,
            "citation_precision_at_5": m.citation_precision_at_5, "citation_precision_at_10": m.citation_precision_at_10,
            "mrr": m.mrr, "multihop_coverage": m.multihop_coverage, "abstention_accuracy": m.abstention_accuracy,
            "outcome": m.outcome, "latency_ms": lat * 1000.0,
        })
    tot_bm25_dur = time.perf_counter() - t_start_all
    ds_res["bm25"] = compute_aggregate_metrics(bm25_cases, bm25_lats, bm25_idx_time, n_docs, get_current_rss_mb())
    ds_res["bm25"]["cases"] = bm25_cases
    print(f"  [BM25 Result] nDCG@10={ds_res['bm25']['metrics']['ndcg_at_10']:.4f}, Recall@20={ds_res['bm25']['metrics']['recall_at_20']:.4f}, QPS={n_cases/tot_bm25_dur:.1f}, P95={ds_res['bm25']['ops']['latency_p95_ms']:.2f}ms", flush=True)

    # 2. GPU Dense
    dense_batch_cands = None
    avg_dense_lat = 0.0
    dense_idx_time = 0.0
    if has_dense and dense_retriever is not None:
        t0 = time.perf_counter()
        dense_retriever.index(corpus_docs, batch_size=512)
        dense_idx_time = time.perf_counter() - t0
        print(f"  [GPU Dense] Indexed {n_docs} docs in {dense_idx_time:.3f}s ({n_docs/dense_idx_time:.1f} docs/sec on RTX 5050)", flush=True)

        query_texts = [c["query"] for c in cases]
        dense_batch_cands, dense_search_time = dense_retriever.retrieve_batch(query_texts, top_k=50, batch_size=512)
        avg_dense_lat = dense_search_time / n_cases
        print(f"  [GPU Dense Search] {n_cases} queries in {dense_search_time:.3f}s ({n_cases/dense_search_time:.1f} QPS)", flush=True)

        dense_cases, dense_lats = [], []
        for i, c in enumerate(cases):
            cands = dense_batch_cands[i]
            retrieved_ids = [f"atom-{idx}" for idx, _ in cands]
            m = evaluate_case_retrieval(c["id"], c["category"], retrieved_ids, c["gold_atom_ids"], False, c["expected_abstention"])
            dense_cases.append({
                "case_id": c["id"], "native_query_id": c.get("native_query_id"), "category": c["category"],
                "expected_abstention": c["expected_abstention"], "recall_at_5": m.recall_at_5, "recall_at_20": m.recall_at_20,
                "recall_at_100": m.recall_at_100, "ndcg_at_10": m.ndcg_at_10, "ndcg_at_30": m.ndcg_at_30,
                "complete_gold_coverage_at_10": m.complete_gold_coverage_at_10, "complete_gold_coverage_at_20": m.complete_gold_coverage_at_20,
                "citation_precision_at_5": m.citation_precision_at_5, "citation_precision_at_10": m.citation_precision_at_10,
                "mrr": m.mrr, "multihop_coverage": m.multihop_coverage, "abstention_accuracy": m.abstention_accuracy,
                "outcome": m.outcome, "latency_ms": avg_dense_lat * 1000.0,
            })
            dense_lats.append(avg_dense_lat)
        ds_res["dense"] = compute_aggregate_metrics(dense_cases, dense_lats, dense_idx_time, n_docs, get_current_rss_mb())
        ds_res["dense"]["cases"] = dense_cases
        print(f"  [GPU Dense Result] nDCG@10={ds_res['dense']['metrics']['ndcg_at_10']:.4f}, Recall@20={ds_res['dense']['metrics']['recall_at_20']:.4f}, P95={ds_res['dense']['ops']['latency_p95_ms']:.2f}ms", flush=True)

        # 3. Hybrid RRF
        rrf_cases, rrf_lats = [], []
        for i, c in enumerate(cases):
            bm25_cands = bm25_retrieved_list[i]
            dense_cands = dense_batch_cands[i]
            rrf_scores = defaultdict(float)
            for rank, (doc_idx, _) in enumerate(bm25_cands, start=1):
                rrf_scores[doc_idx] += 1.0 / (60.0 + rank)
            for rank, (doc_idx, _) in enumerate(dense_cands, start=1):
                rrf_scores[doc_idx] += 1.0 / (60.0 + rank)
            sorted_cands = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)[:50]
            retrieved_ids = [f"atom-{idx}" for idx, _ in sorted_cands]
            m = evaluate_case_retrieval(c["id"], c["category"], retrieved_ids, c["gold_atom_ids"], False, c["expected_abstention"])
            rrf_cases.append({
                "case_id": c["id"], "native_query_id": c.get("native_query_id"), "category": c["category"],
                "expected_abstention": c["expected_abstention"], "recall_at_5": m.recall_at_5, "recall_at_20": m.recall_at_20,
                "recall_at_100": m.recall_at_100, "ndcg_at_10": m.ndcg_at_10, "ndcg_at_30": m.ndcg_at_30,
                "complete_gold_coverage_at_10": m.complete_gold_coverage_at_10, "complete_gold_coverage_at_20": m.complete_gold_coverage_at_20,
                "citation_precision_at_5": m.citation_precision_at_5, "citation_precision_at_10": m.citation_precision_at_10,
                "mrr": m.mrr, "multihop_coverage": m.multihop_coverage, "abstention_accuracy": m.abstention_accuracy,
                "outcome": m.outcome, "latency_ms": (bm25_lats[i] + avg_dense_lat) * 1000.0,
            })
            rrf_lats.append(bm25_lats[i] + avg_dense_lat)
        ds_res["hybrid_rrf"] = compute_aggregate_metrics(rrf_cases, rrf_lats, bm25_idx_time + dense_idx_time, n_docs, get_current_rss_mb())
        ds_res["hybrid_rrf"]["cases"] = rrf_cases
        print(f"  [Hybrid RRF Result] nDCG@10={ds_res['hybrid_rrf']['metrics']['ndcg_at_10']:.4f}, Recall@20={ds_res['hybrid_rrf']['metrics']['recall_at_20']:.4f}, P95={ds_res['hybrid_rrf']['ops']['latency_p95_ms']:.2f}ms", flush=True)

    # 4. GPU HippoRAG PPR
    if has_hipporag and has_dense and dense_batch_cands is not None:
        print("  [GPU HippoRAG PPR] Building bipartite matrix on RTX 5050...", flush=True)
        all_ents = set()
        doc_ents = []
        for d in corpus_docs:
            ents = extract_entities((d.get("title") or "") + " " + (d.get("text") or ""))
            doc_ents.append(ents)
            all_ents.update(ents)
        ent_list = sorted(list(all_ents))
        ent_to_idx = {e: idx for idx, e in enumerate(ent_list)}
        n_ents = len(ent_list)

        # Adjacency tensor (n_ents, n_docs)
        A_matrix = np.zeros((n_ents, n_docs), dtype=np.float32)
        for d_idx, ents in enumerate(doc_ents):
            for e in ents:
                e_idx = ent_to_idx[e]
                A_matrix[e_idx, d_idx] = 1.0

        A_t = torch.tensor(A_matrix, device=DEVICE)
        # Degree normalize
        ent_degs = torch.clamp(A_t.sum(dim=1, keepdim=True), min=1.0)
        A_norm = A_t / ent_degs

        doc_degs = torch.clamp(A_t.T.sum(dim=1, keepdim=True), min=1.0)
        A_t_norm = A_t.T / doc_degs

        # Seed matrix (Q, n_ents)
        E_seed_np = np.zeros((n_cases, n_ents), dtype=np.float32)
        for i, c in enumerate(cases):
            q_ents = extract_entities(c["query"])
            seed_indices = [ent_to_idx[e] for e in q_ents if e in ent_to_idx]
            if seed_indices:
                prob = 1.0 / len(seed_indices)
                for s_idx in seed_indices:
                    E_seed_np[i, s_idx] = prob

        E_seed = torch.tensor(E_seed_np, device=DEVICE)
        E = E_seed.clone()

        t0_ppr = time.perf_counter()
        for step in range(10):
            D = torch.mm(E, A_norm)
            E_next = torch.mm(D, A_t_norm)
            E = 0.85 * E_next + 0.15 * E_seed

        final_doc_scores = torch.mm(E, A_norm) # shape: (Q, n_docs)
        top_ppr_vals, top_ppr_idx = torch.topk(final_doc_scores, k=min(50, n_docs), dim=1)
        torch.cuda.synchronize() if DEVICE == "cuda" else None
        tot_ppr_dur = time.perf_counter() - t0_ppr

        top_ppr_cpu = top_ppr_idx.cpu().numpy()
        avg_ppr_lat = tot_ppr_dur / n_cases

        ppr_cases, ppr_lats = [], []
        for i, c in enumerate(cases):
            # Fallback to dense if zero entity matches
            if np.all(E_seed_np[i] == 0.0):
                cands = dense_batch_cands[i]
                retrieved_ids = [f"atom-{idx}" for idx, _ in cands]
            else:
                retrieved_ids = [f"atom-{doc_i}" for doc_i in top_ppr_cpu[i]]

            m = evaluate_case_retrieval(c["id"], c["category"], retrieved_ids, c["gold_atom_ids"], False, c["expected_abstention"])
            ppr_cases.append({
                "case_id": c["id"], "native_query_id": c.get("native_query_id"), "category": c["category"],
                "expected_abstention": c["expected_abstention"], "recall_at_5": m.recall_at_5, "recall_at_20": m.recall_at_20,
                "recall_at_100": m.recall_at_100, "ndcg_at_10": m.ndcg_at_10, "ndcg_at_30": m.ndcg_at_30,
                "complete_gold_coverage_at_10": m.complete_gold_coverage_at_10, "complete_gold_coverage_at_20": m.complete_gold_coverage_at_20,
                "citation_precision_at_5": m.citation_precision_at_5, "citation_precision_at_10": m.citation_precision_at_10,
                "mrr": m.mrr, "multihop_coverage": m.multihop_coverage, "abstention_accuracy": m.abstention_accuracy,
                "outcome": m.outcome, "latency_ms": avg_ppr_lat * 1000.0,
            })
            ppr_lats.append(avg_ppr_lat)
        ds_res["hipporag_ppr"] = compute_aggregate_metrics(ppr_cases, ppr_lats, dense_idx_time, n_docs, get_current_rss_mb())
        ds_res["hipporag_ppr"]["cases"] = ppr_cases
        print(f"  [GPU HippoRAG PPR Result] nDCG@10={ds_res['hipporag_ppr']['metrics']['ndcg_at_10']:.4f}, Recall@20={ds_res['hipporag_ppr']['metrics']['recall_at_20']:.4f}, CompleteCov@20={ds_res['hipporag_ppr']['metrics']['complete_gold_coverage_at_20']:.4f}, QPS={n_cases/tot_ppr_dur:.1f}, P95={ds_res['hipporag_ppr']['ops']['latency_p95_ms']:.2f}ms", flush=True)

    with open(RUNS_DIR / f"{name}_runs.json", "w", encoding="utf-8") as f:
        json.dump(ds_res, f, indent=2)
    print(f"  Saved raw per-case run results to: {RUNS_DIR / f'{name}_runs.json'}", flush=True)
    return ds_res

def run_evaluation_suite():
    print("========================================================================", flush=True)
    print("Starting S6 Real-Data Baseline Suite on NVIDIA RTX 5050 (SM120)", flush=True)
    print("Timestamp UTC:", datetime.now(timezone.utc).isoformat(), flush=True)
    print("========================================================================", flush=True)

    dense_retriever = GPUDenseRetriever(model_name="sentence-transformers/all-MiniLM-L6-v2", device=DEVICE)
    results_by_dataset = {}

    # 1. BEIR SciFact (Direct/Source Lookup)
    res1 = evaluate_dataset_suite("beir-scifact", has_dense=True, has_hipporag=False, dense_retriever=dense_retriever)
    results_by_dataset["beir-scifact"] = {b: {k: v for k, v in res1[b].items() if k != "cases"} for b in res1}

    # 2. BEIR NFCorpus (Medical Domain)
    res2 = evaluate_dataset_suite("beir-nfcorpus", has_dense=True, has_hipporag=False, dense_retriever=dense_retriever)
    results_by_dataset["beir-nfcorpus"] = {b: {k: v for k, v in res2[b].items() if k != "cases"} for b in res2}

    # 3. BEIR FiQA (Financial QA / Domain Retrieval)
    res3 = evaluate_dataset_suite("beir-fiqa", has_dense=True, has_hipporag=False, dense_retriever=dense_retriever)
    results_by_dataset["beir-fiqa"] = {b: {k: v for k, v in res3[b].items() if k != "cases"} for b in res3}

    # 4. MultiHop-RAG (Multi-hop, Chronology, Abstention)
    res4 = evaluate_dataset_suite("multihop-rag", has_dense=True, has_hipporag=True, dense_retriever=dense_retriever)
    results_by_dataset["multihop-rag"] = {b: {k: v for k, v in res4[b].items() if k != "cases"} for b in res4}

    # 5. BRIGHT (Complex Reasoning / Math / Coding: BM25 on 928,750 docs)
    res5 = evaluate_dataset_suite("bright", has_dense=False, has_hipporag=False, dense_retriever=None)
    results_by_dataset["bright"] = {b: {k: v for k, v in res5[b].items() if k != "cases"} for b in res5}

    # 6. MuSiQue (Compositional Multi-Hop: BM25 on 22,355 queries & 101,962 segments)
    res6 = evaluate_dataset_suite("musique", has_dense=False, has_hipporag=False, dense_retriever=None)
    results_by_dataset["musique"] = {b: {k: v for k, v in res6[b].items() if k != "cases"} for b in res6}

    # 7. BigANN / SIFT1M (Operations / Vector Scale Lane - 100,000 vectors)
    print("\n========================================================================", flush=True)
    print("Evaluating BigANN / SIFT1M Vector Operations (100,000 vectors, isolated operations lane)", flush=True)
    print("========================================================================", flush=True)
    learn_path = RAW_SIFT_ROOT / "sift_learn.fvecs"
    query_path = RAW_SIFT_ROOT / "sift_query.fvecs"
    gt_path = RAW_SIFT_ROOT / "sift_groundtruth.ivecs"

    t0 = time.perf_counter()
    mem_before = get_current_rss_mb()
    learn_vectors = read_fvecs(str(learn_path), max_vectors=100000)
    query_vectors = read_fvecs(str(query_path), max_vectors=1000)
    gt_indices = read_ivecs(str(gt_path), max_vectors=1000)
    idx_load_time = time.perf_counter() - t0
    mem_after = get_current_rss_mb()

    # Fast GPU L2 distance computation on RTX 5050
    t0_q = time.perf_counter()
    learn_t = torch.tensor(learn_vectors, device=DEVICE)
    q_t = torch.tensor(query_vectors, device=DEVICE)

    learn_sq = torch.sum(learn_t ** 2, dim=1) # (100000,)
    q_sq = torch.sum(q_t ** 2, dim=1)         # (1000,)
    dots = torch.mm(q_t, learn_t.T)           # (1000, 100000)
    dists = q_sq.unsqueeze(1) + learn_sq.unsqueeze(0) - 2 * dots
    top10_vals, top10_indices = torch.topk(dists, k=10, dim=1, largest=False)
    torch.cuda.synchronize() if DEVICE == "cuda" else None
    total_q_time = time.perf_counter() - t0_q

    top10_cands = top10_indices.cpu().numpy()

    rec1_hits = 0
    rec10_hits = 0
    for q_idx in range(len(query_vectors)):
        gt_set = set(gt_indices[q_idx][:10].tolist())
        pred1 = top10_cands[q_idx][0]
        pred10 = set(top10_cands[q_idx][:10].tolist())
        if pred1 in gt_set:
            rec1_hits += 1
        rec10_hits += len(pred10 & gt_set) / min(len(gt_set), 10)

    sift_res = {
        "dataset": "bigann",
        "lane": "operations_vector_scale_isolated",
        "vector_count": len(learn_vectors),
        "vector_dimension": 128,
        "query_count": len(query_vectors),
        "indexing": {
            "duration_sec": idx_load_time,
            "throughput_vectors_per_sec": len(learn_vectors) / idx_load_time if idx_load_time > 0 else 0.0,
            "rss_memory_mb": mem_after - mem_before,
            "peak_memory_rss_mb": mem_after,
        },
        "queries": {
            "total_queries": len(query_vectors),
            "total_query_duration_sec": total_q_time,
            "qps": len(query_vectors) / total_q_time if total_q_time > 0 else 0.0,
            "latency_p50_ms": float(total_q_time / len(query_vectors) * 1000.0),
            "latency_p95_ms": float(total_q_time / len(query_vectors) * 1000.0),
            "latency_p99_ms": float(total_q_time / len(query_vectors) * 1000.0),
            "latency_mean_ms": float(total_q_time / len(query_vectors) * 1000.0),
            "recall_at_1": rec1_hits / len(query_vectors),
            "recall_at_10": rec10_hits / len(query_vectors),
        }
    }

    with open(RUNS_DIR / "bigann_operations_run.json", "w", encoding="utf-8") as f:
        json.dump(sift_res, f, indent=2)
    results_by_dataset["bigann"] = sift_res
    print(f"  BigANN SIFT100K: 100,000 vectors indexed in {idx_load_time:.2f}s, QPS={sift_res['queries']['qps']:.1f}, Mean Latency={sift_res['queries']['latency_mean_ms']:.3f}ms", flush=True)

    # Save master distributions summary
    summary = {
        "evaluation_suite": "s6-real-baselines-p005",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "runner_commit": "c0ea9fbf37bc50c88336f198437be031c18d6f64",
        "trace_commit": "f7bd96e9c5e0f9326b53a074024e7ace889f6e36",
        "hardware": {
            "gpu": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "None",
            "sm_capability": list(torch.cuda.get_device_capability(0)) if torch.cuda.is_available() else [],
            "driver_cuda": torch.version.cuda
        },
        "datasets_summary": results_by_dataset
    }
    with open(EVIDENCE_DIR / "baseline-distributions-summary.json", "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)

    print("\n========================================================================", flush=True)
    print("Baseline Evaluation Suite Completed Successfully!", flush=True)
    print(f"Results stored in: {RUNS_DIR}", flush=True)
    print(f"Summary stored in: {EVIDENCE_DIR / 'baseline-distributions-summary.json'}", flush=True)
    print("========================================================================", flush=True)

if __name__ == "__main__":
    run_evaluation_suite()
