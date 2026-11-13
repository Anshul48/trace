<!-- SPDX-License-Identifier: Apache-2.0 -->
# TRACE roadmap

Design direction, not promises. No dates. Most of this does not exist yet;
what runs today is in the [status table](../README.md#status-what-runs-what-is-experimental-what-is-design)
of the README.

## The self-organising store

- **Outline.** Split the library into small pieces of meaning and let the
  pieces gather into groups, then groups of groups, with each piece keeping
  its links upward. The same piece may sit in more than one group, and use
  would reshape the grouping: travelled links strengthen, unused ones fade.
  *Design; one early experiment, see the status table.*
- **Learning from outcomes.** Strengthen links that lead somewhere useful,
  weaken the rest, and roll a change back when it hurts. Tried on
  development data (real library code, simulated feedback): a gain only
  when the correct answer is fed back (see [docs/design](design/README.md)).
- **Sleep.** Replay the day's work offline, compressing, distilling and
  deleting, behind a gate that can reject a bad proposal. Tried offline
  in four tests; no benefit shown (see [docs/design](design/sleep.md)).
- **Repeated work to scripts.** Record slow, correct, deliberate work,
  verify it, and replace repeats with a fast script that replays it.
  Experimental on one task series (see the status table in the README);
  not shown as a general capability.
- **Top-down prediction.** A cheap guess places each new piece; where the
  guess and the built grouping disagree, the grouping is rebuilt locally.
  Designed.
- **Several stores.** Several stores built at different times over one
  unchanged copy of the text, with views that need not agree. Designed;
  after one store works.

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
