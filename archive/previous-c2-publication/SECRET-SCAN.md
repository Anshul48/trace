# Secret scan (final candidate tree)

Date: 2026-10-14 (UTC). Scope: entire staged `trace-final-release/` tree
(1380+ tracked files, `.git/` and `.venv/` excluded), **including larger
files** (no size cap: 1.4 MB `rows.jsonl`, 440 KB wheel, 389 KB
derivation map, 214 KB verdict, 182 KB curated fixture all scanned).

Result: **CLEAN — no credentials, keys, tokens, private-key blocks, or
`.env` files.** Every pattern hit was classified from context (values
never printed).

## Method (all read-only)

1. `.env` hunt: tracked-path match for `.env` → 0 hits. `.venv/` is
   git-ignored and unstaged. No `.pem`/`.key` members in the vendored
   wheel (95 members listed, none suspicious, no `__pycache__`).
2. Hard patterns over all tracked bytes (`git grep`, no size limit):
   `BEGIN … PRIVATE KEY` → 0; `AKIA…` → 0; `ghp_/gho_/xox/sk-ant-/AIza`
   → 0. Wheel `strings` hard-pattern scan → 0.
3. Name scan (`api_key|apikey|aws_access|aws_secret|bearer …`): 40 files.
   All classified: credential-handling code by design (auth/key-entry/
   gateway/migration paths in `src/trace/v2/`, `migrations/`,
   `benchmarks/enter_sail_key.py`, `prompt_gui_key`, bakeoff runners,
   `scripts/connect_llm.py`, `test_llm_integration.py` — identifiers,
   `os.environ.get`/`input()` plumbing, header lookups, hash/ciphertext
   variables, Terraform secret-manager *references*); benchmark corpus
   SQL/game text containing password-like words (bulls-and-cows,
   UnitSchedule queries — corpus content, not credentials); docs
   describing `SAIL_API_KEY` env custody with a 3-char placeholder;
   and new-tree prose-only words ("no secrets …", fixture paragraphs
   about Bearer tokens/HMAC/JWT with zero values, "No secrets in git").
4. Value scan (secret-word assignments): 24 files, every quoted value
   checked by length/placeholder-keyword test — all variable plumbing
   (`api_key=api_key`), key names (the `SECRET_KEYS` tuple holds
   lowercase identifier names, not values), resource-name strings, or
   placeholders. The runtime secret generator uses OS randomness and
   embeds no credentials.
5. `scale_100k.db*` ruling (kept in tree, scanned): the 6.5 MB SQLite
   + shm/wal work files from the Aug-2026 S7 100K gate are a LIVE
   dependency of `run_100k_qualification.DEFAULT_DB_CANDIDATES` and two
   committed scaffold tests, so removal would break the suite (verified:
   removal flipped 2 tests red; restore flips them green). Content
   check: sensitive tables (`api_keys`, `webhooks`,
   `model_call_audits`, …) hold 0 rows; content tables hold no
   PII/credentials (0 emails, 0 credential-pattern hits in db bytes)
   — only short public-reference snippets (`hot_inbox.content`, max
   1200 chars, public-encyclopedia-style; same bytes in the tracked
   `objects/…` files) alongside UUIDs/offsets/hashes/event
   envelopes; `strings` hard-pattern scan → 0 hits.
   Provenance is documented in the co-shipped packet (`packet.md`:
   "admitted real data" experiment + human-gate dossier). Verdict:
   needed + not shown private → kept, with hashes in MANIFEST.md.

## Standing rules for this tree

- `.gitignore` excludes `.env` / `.env.*`; no credential material is
  staged. Reviewer re-run: steps 1–4 above against the candidate commit.
- The Gemini hero illustration (if any) arrives as a bare image file
  from the coordinator; generation credentials never enter this tree.
