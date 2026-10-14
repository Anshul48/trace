"""Trace Scale Datasets Ingestion & Staging Suite.

This package provides high-throughput fetchers, parsers, and staging pipelines
for real-world scale datasets (1M - 1B tokens):
1. Enron Corporate Email Corpus (`fetch_enron.py`)
2. Linux Kernel Git Archives & LKML (`fetch_lkml.py`)
3. SEC EDGAR 10-K & 10-Q Financial Filings (`fetch_edgar.py`)
4. Wikipedia / RedPajama Bounded-Memory Stream (`fetch_wikipedia_stream.py`)
5. MuSiQue & 2WikiMultiHop Reasoning Graphs (`stage_multihop.py`)
"""

__all__ = [
    "fetch_enron",
    "fetch_lkml",
    "fetch_edgar",
    "fetch_wikipedia_stream",
    "stage_multihop",
]
