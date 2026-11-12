<!-- SPDX-License-Identifier: Apache-2.0 -->
# Sleep: an offline tidy that must earn its keep

**FOR A NEW READER.** Once a day the store would stop taking new material and tidy itself: replay recent use, merge groups that duplicate each other, split groups that should never have merged, fade links nobody travels, and throw away one-off clutter. Every tidy runs on a copy first and is kept only if the tidied store predicts held-out material no worse than before; otherwise it is rolled back and logged.

## What exists today

DESIGN. No sleep cycle runs anywhere. The raw material it would work on (usage logs, repeated traces) exists only as scattered run records.

## Latest measured number

None. No sleep run has shown a benefit anywhere as of 12 November. The next step, before any new build, is to define the benefit and the compute-matched control that would show it: a sleep that beats doing nothing, beats keeping a random sample, and beats keeping only recent material, with the rollback gate switched on.

## What it does not show

Everything about sleep is unshown: no tidier store, no cheaper repeats after a cycle, no gate catching a bad proposal, no cross-region links proposed and kept. The design notes for the other four pieces describe what little is measured there.

## What would prove it wrong

If sleep cycles never beat the random-sample control on held-out material, or if the rollback gate fires on every proposal including good ones, offline consolidation adds nothing and the design must do without it.
