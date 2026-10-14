## Summary

## Checklist
- [ ] No changes under `freeze-src/` or `archive/` (byte-exact records)
- [ ] `python3 tools/verify_freeze.py` prints `entries=207 ok=207 missing=0 mismatch=0`
- [ ] `python3 tools/check_receipts.py` and `python3 tools/check_links.py` pass
- [ ] Any number quoted in docs is read from `receipts/` (file + field named below)
- [ ] No corpus, weights, store, credentials, or new 10M run
