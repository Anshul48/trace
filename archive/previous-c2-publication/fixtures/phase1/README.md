# Public Phase 1 fixture

This small synthetic corpus is safe to publish and is intended for repeatable
local smoke tests. It does not stand in for private owner-approved engineering
corpora or for the 100,000 and 1,000,000 source-atom scale runs.

Run it locally:

~~~powershell
trace ingest --data-dir .\fixture-data .\fixtures\phase1\public-corpus.jsonl
trace query --data-dir .\fixture-data "event ledger"
trace verify --data-dir .\fixture-data
~~~

The checked-in public judgments contain exactly 100 frozen query judgments
spanning direct lookup, dependency, contradiction, chronology, navigation, and
out-of-scope requests. They use stable record IDs; the fixture runner maps
those IDs to locally created atom IDs after ingestion.

~~~powershell
trace run-fixture --data-dir .\fixture-data
~~~

The generator can regenerate the checked-in JSON deterministically. A fixture
run produces measured query evidence; add the declared hardware profile,
token measurements, navigation-review decisions, and defect record before
evaluating it with the pilot gate.
