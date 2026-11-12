<!-- SPDX-License-Identifier: Apache-2.0 -->
# series-compile: synthetic repeated-task-series demo

## Idea in plain words

When the same job repeats with only the details changed (new numbers,
dates, ids, paths), the repeats form a series. A series can be replaced
by one small script, written once and then checked: find the repeats, replay the script over every
past input to check it, and refuse any input that looks unlike the
series, handing it to a person instead. This package shows each step on
invented data: packing summaries for imaginary stores, shipments and
weights. Nothing here comes from any real workload.

## One command

```sh
python3 -I series_compile.py demo
```

It builds five synthetic datasets in a temp dir, runs detect, shadow
and guard, prints one table, and removes the temp dir. Stdlib only.

## Expected output

Byte-exact text also kept in `EXPECTED_OUTPUT.txt`:

```
SYNTHETIC repeated-task-series to checked-script demo (SYNTHETIC DATA ONLY)
dataset | check           | outcome
--------+-----------------+--------
a       | detect          | SERIES count=40 template="Packing summary for DEMO store <ID> on <DATE>: shipment <ID> staged at <PATH>. Count items and total weight."
a       | shadow-script   | matched=40 mismatched=0
a       | copy-previous   | matched=0/39 control: repeat last output
b       | detect          | SERIES count=40 template="Packing summary for DEMO store <ID> on <DATE>: shipment <ID> staged at <PATH>. Count items and total weight."
b       | shadow-script   | matched=20 mismatched=20 mismatch-block=runs-021-to-040 method-changed-after-run-20
b       | copy-previous   | matched=0/39 control: repeat last output
c       | detect          | NO-SERIES briefs=40 max-group=1 need>=5
c       | shadow-script   | SKIPPED no-series
d       | detect          | SERIES count=40 template="Packing summary for DEMO store <ID> on <DATE>: shipment <ID> staged at <PATH>. Count items and total weight."
d       | shadow-script   | matched=39 corrupted=1 corrupted-run=017
d       | guard-corrupted | REFUSED corrupted-input weight='N/A' -> handoff-to-person
e       | detect          | SERIES count=30 template="Shipping estimate for DEMO store <ID> on <DATE>: shipment <ID> staged at <PATH>. Total weight by worker convention."
e       | shadow-script   | vs-alpha=30/30 vs-beta=0/30 vs-gamma=0/30 matches-one-worker-only
e       | worker-agree    | alpha-beta=0/30 alpha-gamma=0/30 beta-gamma=0/30
guard   | valid-input     | ALLOWED {"item_count":20,"total_weight":116.33}
guard   | new-schema      | REFUSED new-schema -> handoff-to-person
guard   | new-slot-value  | REFUSED new-slot-value store="WH-99" not-in-series -> handoff-to-person
SYNTHETIC DATA ONLY: invented stores, shipments and weights; no claim about any real workload.
```

Reading the rows: (a) 40 repeats of one template, script matches all 40
while repeating the last output matches none; (b) the method changes
after run 20, visible as a mismatch block over runs 21-40; (c) 40
one-offs, so no series; (d) one corrupted input, matched nowhere and
refused by the guard; (e) three workers read one brief three ways, so
the script matches one worker only and the worker-agreement row shows
why. The guard rows allow a seen input and refuse a new schema and a
new store value.

## What it does NOT show

* The candidate script is written by hand, and it is the same function the generator uses to produce the recorded outputs of dataset (a). The 40 of 40 match is therefore by construction. The demo shows the checking harness (detection, shadow comparison with its two controls, the guard), not automatic writing of a script.
* The data is synthetic: stores, shipments, shelves, weights and worker
  habits are invented by `gen` from fixed seeds. Repeats here prove
  nothing about any real workload.
* The method is tiny on purpose (count items, add weights). Real jobs
  need their own script and their own checks.
* The guard is deliberately strict demo logic: it refuses anything the
  series did not show, even harmless novelties. Refusal means "ask a
  person", never silent acceptance.
* `copy-previous` and worker agreement are controls, not rivals: they
  show what a hollow match would look like.

## Layout

* `series_compile.py` -- gen, detect, shadow, guard, demo in one file.
* `tests/test_smoke.py` -- hermetic smoke suite; run it with
  `python3 -W error::ResourceWarning -m unittest discover` from here.
* `EXPECTED_OUTPUT.txt` -- byte-exact `demo` output; running `demo`
  twice must reproduce it byte for byte.

## License

Apache-2.0. See the SPDX line at the top of each source file.
