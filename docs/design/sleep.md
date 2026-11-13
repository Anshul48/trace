<!-- SPDX-License-Identifier: Apache-2.0 -->
# Sleep: an offline tidy that must earn its keep

**FOR A NEW READER.** Once a day the store would stop taking new material and tidy itself: replay recent use, merge groups that duplicate each other, split groups that should never have merged, fade links nobody travels, and throw away one-off clutter. Every tidy runs on a copy first and is kept only if the tidied store predicts held-out material no worse than before; otherwise it is rolled back and logged.

## What exists today

EXPERIMENTAL, no benefit shown. Sleep passes have been run in four tests, each offline on development data or on a copy of a store. The safety parts work: the gate, exact rollback, and blocking a deliberately corrupted pass. Nothing is switched on in any served store.

## Latest measured number

On 12 to 13 November, four tests showed no benefit that could be put down to sleep. Where numbers improved after a sleep pass, a control without sleep matched them: once a random control (cost fell 49 percent in both), once a better search. (As reported by the builders, not yet rerun.)

## What it does not show

No benefit of sleep is shown: no tidier store, no cheaper repeats after a cycle, no links between distant groups proposed and kept. The design notes for the other four pieces describe what little is measured there.

## What would prove it wrong

If sleep cycles never beat the random-sample control on held-out material, or if the rollback gate fires on every proposal including good ones, offline consolidation adds nothing and the design must do without it.
