# Contributing to TRACE

Thank you for looking. TRACE is a research prototype, so the rules are stricter than usual: the point of the repository is that its claims can be checked.

## The rules

- **Never edit `freeze-src/`.** It is the tested engine, 207 files. Any edit breaks `python3 tools/verify_freeze.py`, which must keep ending with `entries=207 ok=207 missing=0 mismatch=0`. Put new code outside it (`tools/`, `docs/examples/demo/`, `tools/demo-app/`).
- **No new numbers without a record.** Every number in the README and on the website must trace to a file in `receipts/` (or to a measurement file named in the evidence page). Do not run a large build "to check something": the larger builds are billed, multi-hour hardware.
- **Say what was measured, and its scope.** Write "50 test searches", "our library and method", "stored size on disk", "one of four equal parts" next to 0.79%, and "short of the 100M target by 0.11%" next to 99.9M. Do not write "beats", "fastest", "faster", "low memory", "scales to a billion" or "works on public benchmarks".
- **Explain our words.** Brain-inspired words are fine only when they are accurate, always as "inspired by", never "works like the brain", and each with a plain-words explanation. Avoid unexplained jargon (shard, recall@10, nDCG, BM25, lanes): write ordinary keyword search, checkable record, piece and group instead.
- **No corpus, store, weights or credentials in commits.** See [SECURITY.md](SECURITY.md).

## Changing the website or the README

The website in `docs/` and the root `README.md` are generated, so they cannot drift:

1. Edit the sources: `docs/source/pages/*.html`, `docs/source/partials/*.html`, `docs/source/README.src.md`.
2. If a capability changes (a "Working today", "Prototype" or "Not built yet" label), edit [`docs/status.json`](docs/status.json). A capability may be marked `built` only if its `evidence` path exists in the repository.
3. To swap a film, edit [`docs/demos/films.json`](docs/demos/films.json) (see the Demos page for how).
4. Run `python3 tools/build_site.py`, then commit the generated files with your change.

The generated files are checked: `python3 tools/build_site.py --check` fails if `docs/` or `README.md` differs from what the sources produce.

## Checks before a pull request

```bash
python3 tools/verify_freeze.py          # entries=207 ok=207 missing=0 mismatch=0
python3 tools/check_receipts.py         # receipts ok: ...
python3 tools/check_links.py            # links ok, status.json evidence paths exist
python3 tools/build_site.py --check     # site ok
python3 docs/examples/demo/synthetic_recall.py
```

CI runs the same checks. The [pull request template](.github/pull_request_template.md) lists the rest.

## Reporting a wrong number

If a number or sentence on the site does not hold, that is the most useful report we can get: open an issue with the "A claim or number looks wrong" form.
