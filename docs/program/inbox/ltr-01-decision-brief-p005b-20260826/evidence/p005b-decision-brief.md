# Decision Brief P-005b: Large-Token Retrieval Readiness Thresholds

> **Decision Subject:** DEC-P-005b (Numerical Release Thresholds, Hardware Profiles, and Capacity Accounting)  
> **Human Gate:** Human Gate B2  
> **Authority Level:** C3 (Proposal Submitted for Formal Human Owner Approval)  
> **Date:** 2026-08-26  

---

## 1. Executive Summary

DEC-P-005b amends the early-scale hardware and resource-accounting clauses of DEC-P-005 to establish rigorous, realistic criteria for large-token memory and retrieval while leaving all truth, durability, bounded-work, and quality invariants strictly intact.

## 2. Binding Profiles & Thresholds

| Topic | Rule in DEC-P-005b | Rationale |
| :--- | :--- | :--- |
| **Core Reference Tier (R16)** | Declared 16 GiB host-RAM reference machine. No OOM, allocator retry loop, or active paging. | Proves single-node viability on reference local hardware. |
| **Peak Memory Bound** | Peak program-owned process-tree RSS $\le \mathbf{8.0\text{ GiB}}$ for 100K corpus. | Leaves 8 GiB headroom for OS and auxiliary services on 16 GiB host. |
| **CPU Throughput Profile (C)** | $\ge \mathbf{150\text{ docs/sec}}$, with tokens/s, atoms/s, and bytes/s reported co-primarily. | Preserves CPU floor while measuring token work. |
| **GPU Throughput Profile (A6)** | $\ge \mathbf{500\text{ docs/sec}}$ when GPU embedding/index counters confirm GPU acceleration; peak VRAM $\le \mathbf{6.0\text{ GB}}$. | Distinguishes accelerated throughput without conflating with capacity proof. |
| **Scale Units** | Ingestion reports lead with $T$ (tokens), $N$ (atoms), $B$ (raw bytes), and throughput in tokens/sec and bytes/sec. | Prevents document-size bias from masking real work. |
| **Retrieval Quality Floors** | Non-inferiority to strong baselines: lower 95% bootstrap bound $\ge -0.010$ on primary metric, no lane regression $\ge 0.030$. Multi-hop and complex reasoning retain floors. | Ensures Trace does not regress vs baselines while proving scale. |
| **Durability & Correctness** | 100.0% atom retention, 0.0% hash drift, 100.0% byte offset recovery, $\Delta = 0$ repeat erasure, max graph degree $\le 50$, walk depth $\le 15$, graph time $\le 35\text{ ms}$, storage multiplier $\le 3.0\times$. | Non-negotiable truth and bounded economics. |
| **Crash & Recovery** | Verified event replay with 100.0% rebuild parity. | Durability is an active component of scale. |

## 3. Recommendation

Owner accepts **DEC-P-005b** to govern Waves R1, R2, and R3.
