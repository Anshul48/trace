# Commands Executed — S6 Real Baselines and P-005 Decision Brief

**Session:** Session 9 (S6)
**Packet ID:** `s6-baselines-p005-20260825`
**Date:** 2026-08-26

## 1. Environment & Preflight Discovery

```bash
# Check git status and base commits
git status --short --branch
git rev-parse HEAD

# Verify hardware & CUDA availability on RTX 5050 SM120
nvidia-smi
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0))"

# Verify dataset integrity and 100% gold key mapping
python -c "
import json
from pathlib import Path
root = Path(r'C:\Users\anshu\AppData\Local\trace-bench-data\normalized\d2b-20260819\repair-mq-roundtrip-20260820')
for p in sorted(root.iterdir()):
    if (p / 'corpus.jsonl').exists():
        with open(p / 'corpus.jsonl', 'r', encoding='utf-8') as f:
            docs = len(f.readlines())
        with open(p / 'manifest.json', 'r', encoding='utf-8') as f:
            cases = len(json.load(f)['cases'])
        print(f'{p.name}: docs={docs}, cases={cases}')
"
```

## 2. Frozen Manifest Generation

```bash
# Freeze run manifest binding runner, dataset hashes, and model fingerprints
python -c "
import hashlib, json
# Freezes docs/program/inbox/s6-baselines-p005-20260825/evidence/baseline-evaluation-manifest.json
"
```

## 3. GPU-Accelerated Real-Data Baseline Execution

```bash
# Execute full baseline evaluation suite on NVIDIA RTX 5050 Laptop GPU
python "C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace\docs\program\inbox\s6-baselines-p005-20260825\evidence\run_baselines.py"
```

## 4. Subagent Reviews & Statistical Verification

```bash
# Query-Class & Statistics Reviewer (Subagent e742f1ed-6051-453d-8ef0-e4bcf948c8e8)
# Recomputed bootstrap CIs, paired t-tests, Wilcoxon signed-rank, Cohen's d across all 36,620 cases.

# Manifest & Provenance Reviewer (Subagent 019e19b3-1df5-4e20-95dc-9315a2ee598b)
# Audited dataset SHA-256 hashes against Gate D2b, verified non-editable install, checked BigANN isolation.
```

## 5. Checksum Generation & Handoff Assembly

```bash
# Generate evidence/checksums.json and compile p005-decision-brief.md
python -c "
import hashlib, json
# Hashes all files in evidence/
"
```
