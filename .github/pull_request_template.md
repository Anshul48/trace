## Summary

## Checklist
- [ ] No changes under `freeze-src/` (`python3 tools/verify_freeze.py` prints `entries=207 ok=207 missing=0 mismatch=0`)
- [ ] `python3 tools/check_receipts.py` and `python3 tools/check_links.py` pass
- [ ] If I touched `docs/` or `README.md`: I edited `docs-src/` and ran `python3 tools/build_site.py`, and `--check` passes
- [ ] Any number in docs is read from `receipts/` (file named below), with its scope
- [ ] If a capability changed, `docs/status.json` changed with it (a `built` item has an evidence file that exists)
- [ ] No corpus, weights, store, credentials, or large new run
- [ ] Wording: no "beats", "faster", "low memory", "scales to a billion" or "works on public benchmarks"; brain-inspired words are "inspired by" and explained

Source of each number (file and field):
