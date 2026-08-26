# S1 — Benchmark Foundation Owner

## Mission

Make `trace-bench` a reproducible, fail-closed evaluation component. S1 owns
the external benchmark repository and its runner contract; it does not modify
Trace-Lite or Trace product code and does not stage datasets.

The lane has two ordered packets:

1. **B0:** source identity and Git bootstrap.
2. **B1:** explicit modes, fail-closed certification behavior, error receipts,
   provenance mappings, and metric correctness.

## Start condition and boundaries

Start after S0 records P-007/P-008 and provides a lease. Refresh the actual
unversioned tree before editing. Preserve caches, prior results, and unknown
files; add ignore rules rather than deleting them.

Owned root:

```text
C:\Users\anshu\OneDrive\Documents\Code\Utilities\trace-bench
```

Legacy surfaces remain in Trace-Lite for regression/development only:

- `trace-lite/benchmarks/runner.py`;
- `trace-lite/src/trace_lite/engines/benchmark.py`.

They are not the certification boundary and must not be silently removed in
B1.

## B0 — Git/source bootstrap

1. Capture a source-only inventory and exclude caches, result runs, egg-info,
   virtual environments, pycache, and downloaded data from source identity.
2. Initialize Git in place without inventing a remote or altering user content.
3. Add a narrowly scoped `.gitignore` and a source manifest documenting every
   included file and excluded generated surface.
4. Commit the baseline and create an annotated local foundation tag. Record
   commit/tag hashes and the exact clean-clone verification command.
5. Verify that a local clone contains only the intended source and can inspect
   package metadata without needing data or providers.
6. Record dependency/import problems rather than making an unpinned editable
   Trace-Lite import appear healthy.

B0 does not download datasets, invoke providers, or implement runner behavior.

## B1 — Fail-closed runner

### Explicit modes

Require an explicit mode rather than an implicit default:

- `unit`: isolated deterministic tests; mocks may be allowed;
- `regression`: internal fixtures and local developer checks; never
  certification-eligible;
- `exploratory`: real data may be used for development; outputs remain
  non-certifying;
- `certification`: only pinned real data, pinned source artifacts, strict
  provider identity, and complete receipts are legal.

The mode must be present in the run manifest and result files. Certification
must reject mock providers, editable imports, missing manifests, synthetic
data, insecure TLS, hidden fallbacks, and unhandled stage failures.

### Source and package identity

Require a reproducible Trace-Lite artifact identity: pinned commit/wheel hash,
package version, Python/runtime version, dependency lock/fingerprint, and
configuration hash. A dynamic import from an arbitrary working directory is
not certification evidence.

Preserve native dataset IDs, query IDs, document IDs, segment IDs, and source
hashes. Every flattened internal ID must have a reversible mapping back to the
official source record.

### Fail-closed stages

Define explicit preflight, acquisition, indexing, query, metric, and manifest
stages. Any exception must produce a structured error receipt and mark the case
or run failed/blocked. Do not catch an indexing/query exception and return an
empty candidate list. Do not retry with certificate verification disabled.

Forbidden behaviors to remove or guard:

- default `mock_llm=True`;
- synthetic adapter data after download failure;
- flat-search fallback after organize/index failure;
- bare exception swallowing;
- empty results treated as abstention;
- expected abstention receiving perfect retrieval metrics;
- hardcoded `organization_coverage = 1.0`;
- absent source coverage defaulting to `1.0`;
- completion-order pairing instead of stable query-ID pairing.

### Metric semantics

Represent query outcomes separately:

`success`, `explicit_abstention`, `empty_result`, `query_failed`, and
`excluded`.

Positive retrieval metrics use only their declared relevant denominator. An
empty result on a positive-evidence query has zero retrieval contribution; it
does not become an abstention. Expected-abstention cases affect abstention
metrics only. Exclusions require a reason and cannot silently disappear.

### Manifests and receipts

Define schemas for run manifest, dataset admission, source mapping, model/provider
fingerprint, result case, and error receipt. Include schema versions and
content hashes. Missing or malformed manifests fail preflight. The runner must
write a machine-readable result plus a human-readable summary without claiming
certification.

## Tests and acceptance

Add focused tests for every forbidden path, including negative tests for:

- missing source identity;
- mock provider in certification;
- unavailable provider;
- missing/unadmitted/checksum-mismatched dataset;
- synthetic substitution;
- insecure TLS;
- organization/index/query exceptions;
- empty positive retrieval;
- expected abstention metric isolation;
- missing evidence mapping;
- unstable query pairing;
- fabricated coverage;
- forced flat fallback.

Run unit/regression tests with external scratch paths. Do not run a public
certification benchmark in B1. Certification eligibility remains false until
V1a and the data/evaluation gates complete.

## Subagents

Use a read-only fallback auditor and a packaging/test-matrix reviewer. They may
inspect source and draft cases. Only S1 or one explicitly leased writer edits
runner code; no subagent stages data or edits Trace-Lite.

## Required handoff

Include B0 commit/tag/source-manifest hashes, B1 diff/commit, mode matrix,
receipt schemas, negative-test results, package identity procedure, known
limitations, and the exact V1a input manifest. State clearly that no data was
downloaded and no certification claim was made.

## Stop conditions

Stop if the external tree contains unexpected ownership, source identity cannot
be made reproducible, a provider/data fallback remains reachable in
certification, or the requested behavior would require changing Trace-Lite
product code outside this lane.
