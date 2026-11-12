<!-- SPDX-License-Identifier: Apache-2.0 -->
# TRACE roadmap

Design direction, not promises. No dates. Most of this does not exist yet;
what runs today is in the [status table](../README.md#status-what-runs-what-is-experimental-what-is-design)
of the README.

## The self-organizing store

- **Self-organizing ontology.** Atoms of meaning gather into clusters, clusters
  gather under centroids, and every atom keeps its links upward.
  Multi-membership: the same atom can sit under more than one parent.
  Use reshapes the structure: travelled edges gain energy, unused ones decay.
- **Bottom-up organiser.** Builds the clusters and centroids from the atoms,
  without being told how many groups there are. Experimental.
- **Top-down predictor and prediction error.** A cheap guess places each new
  atom; the distance between the guess and the build drives local
  restructuring. Designed.
- **Plastic layer.** Outcomes strengthen or weaken links, with rollback when a
  change hurts. Small toys only so far.
- **Sleep consolidation.** Offline replay that compresses, distills and decays
  the store, behind a commit gate that can reject a bad proposal. Designed;
  a benefit is shown nowhere yet.
- **System 2 to System 1 trace-to-skill.** Slow, correct, deliberate work is
  recorded, verified, and compiled into fast structure that replays without
  the slow path. As a capability this is not shown anywhere yet.
- **Society of cortexes.** Several stores built at different times over one
  byte-exact vault, with views that need not agree. Designed; phase 2, after
  one cortex works.

## How the design is tested

Behaviour first, on a planted testbed with known truth, then on real data:
the planted hierarchy must be recovered past flat baselines, prediction error
must drive restructuring without collapsing old concepts, and use must reshape
structure against a shuffled control. Pass lines are written before runs.
Search scores are never the headline.

## Near-term engineering

- A download of the whole library, so anyone can re-run the 100M numbers.
- A resident search server: open each part once, answer many questions.
- TRACE on public benchmarks (BEIR first) with full-run records.
- An outside check of our numbers.
