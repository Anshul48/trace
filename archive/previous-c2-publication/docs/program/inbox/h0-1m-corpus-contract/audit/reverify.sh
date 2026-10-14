#!/usr/bin/env bash
# P0 audit re-verification. Exits nonzero on the first failure.
# Run from the repo root on branch p11-h0-seal-repair.
# Full suite (~12 min) is intentionally manual; see tail.
set -u
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT" || exit 1
fail() { echo "REVERIFY-FAIL: $1"; exit 1; }

echo "== 1. tracked tree must be clean (packet is additive-only) =="
[ -z "$(git diff HEAD --name-only)" ] || fail "tracked modifications present"
echo OK

echo "== 2. packet tests (25) =="
.venv-linux/bin/python -m pytest tests/test_h0_1m_seal.py tests/test_h0_1m_adopt.py -q \
  || fail "packet tests red"

echo "== 3. frozen BEIR checks (must PASS unmodified) =="
python3 benchmarks/verify_dataset_checksums.py \
  --manifest benchmarks/manifests/beir_musique_frozen_v1.json --root . \
  || fail "frozen checksum check red"
python3 benchmarks/run_frozen_retrieval_baseline.py --verify-receipt \
  --manifest benchmarks/manifests/beir_musique_frozen_v1.json \
  --dossier docs/program/inbox/cap-ret04/retrieval_baseline_dossier.json \
  --receipt docs/program/inbox/cap-ret04/verification_receipt.json \
  || fail "frozen retrieval baseline red"

echo "== 4. help entry points =="
for cmd in "benchmarks/verify_1m_checksums.py" "benchmarks/verify_1m_independent.py" \
           "scripts/seal_1m_manifest.py" "scripts/sign_gate_manifest.py"; do
  python3 "$cmd" --help >/dev/null || fail "$cmd --help red"
done
echo OK

echo "== 5. independent checker on provisional manifest =="
python3 benchmarks/verify_1m_independent.py \
  --manifest docs/program/inbox/h0-1m-corpus-contract/provisional_1m_manifest.json \
  || fail "independent checker red"

echo "== 6. SHA inventory (packet files) =="
G=docs/program/inbox/h0-1m-corpus-contract
sha256sum -c - <<EOF || fail "SHA mismatch"
a3cc70ae5aec7b3a293b13987c913a536e8393d4f701a741c902a78f5b2aba73  benchmarks/verify_1m_checksums.py
f752d64b51f764219481680a2d616b882e59da190538250979aa05f9cbadd350  benchmarks/verify_1m_independent.py
63595eb159e92f19afd2966a32288734b45ae7a97f7ebbc9ee5d073ba4318e21  scripts/sign_gate_manifest.py
937fb037470fe0b60e8dcc6d22ce02889b190014e95930d91a187320c7e96d91  scripts/seal_1m_manifest.py
b1e3ac82b3d3a7598eb646cab5d77ce490fe2346c8cff74daa7313b93781c695  tests/test_h0_1m_adopt.py
72f2bcf06e802e700033ebc2759231db263401c231859d3f099d5240e70dd7ca  tests/test_h0_1m_seal.py
d39a2d0d1a57d83b14882e95dddb80bf1854a6342e14074ea492e075cccfd88b  $G/gate_manifest.json
4f4deb50446f8325f676c3ee2618dfc3059eb78b5551e4855aef932bfe3c8c3d  $G/provisional_1m_manifest.json
50f3ab5c477f81372ca17dbcb3dcc6df6f81f5dea9dbfc386f0cde3eae8bf75f  $G/selection_record.json
e55a901dae1670131e1c273559c851ce1e1ac0dc6106f39da13bba18b3ebaa48  $G/selection_reconciliation.json
0560589ea09ae1e9b96fd7902643e870392ea3a25fb1726ef04e6b98abca96a7  $G/selection_reconciliation.md
EOF

echo "REVERIFY-PASS (fast checks). Manual remainder:"
echo "  .venv-linux/bin/python -m pytest tests/ -q"
echo "  expect: 494 passed, 3 xpassed (baseline 469/3 + 13 adopt + 12 seal)."
