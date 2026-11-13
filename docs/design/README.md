<!-- SPDX-License-Identifier: Apache-2.0 -->
# Design notes

Five short notes on where TRACE is headed, each written for a new reader:
the idea in plain words, what exists today, the latest measured number,
what it does not show, and what would prove it wrong.

- [The grouping](ontology.md): an outline that builds and rebuilds itself.
- [The organiser](organiser.md): grouping without being told how many groups.
- [The top-down guess](top-down-prediction.md): placing new pieces cheaply.
- [Repeated work to scripts](system2-system1.md): replacing slow repeats.
- [Sleep](sleep.md): an offline tidy that must earn its keep.

Learning from outcomes has no note yet. Latest result (12 to 13 November,
development data, as reported by the builders, not yet rerun): learned
links raised accuracy by 0.10 to 0.18 over fixed groups only when the
correct answer was fed back after every query. With only right-or-wrong
feedback the gain was 0.03; with feedback on a fifth of queries, or late,
about 0. No gain is shown without being given the correct answers.
