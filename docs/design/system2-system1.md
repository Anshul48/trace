<!-- SPDX-License-Identifier: Apache-2.0 -->
# Repeated work to scripts: replacing slow repeats with fast replays

**FOR A NEW READER.** Some work repeats: the same task, nearly the same inputs, solved slowly each time. The design records these slow runs, and where they agree it would replace the repeat with a fast script that recomputes the same outputs. The slow path would stay available as a fallback, and a script that ever disagrees would be discarded.

## What exists today

EXPERIMENTAL. For one repeated task from our own task history, a script was written that reproduced the recorded outputs. It ran beside the recorded work; nothing was switched over. A synthetic demo of the checking steps ships in this repo at `experiments/series-compile`. Nothing else runs.

## Latest measured number

On 12 November, on our own task history: a script written from the task description and two recorded runs, with one fix after the first comparison, reproduced every data field of 121 past runs of a task that had been run 122 times (checked by rerun; in 113 of the 122 runs the inputs were the same as in the run before). Of thirteen repeated tasks tried, this one matched on all 121 past runs and two more matched most later runs (as reported by the builders, not yet rerun). Not shown: writing the script automatically, or a skill learned from varied work.

## What it does not show

It does not show scripts learned from varied inputs (nearly all inputs here were unchanged), a skill that generalises to new tasks, or repeat work getting cheaper over time across a workload. The demo in this repo uses invented data and proves nothing about real work.

## What would prove it wrong

If replaced repeats cannot match the slow path on held-out inputs from the same task, or if the cost per repeat never falls as history grows while a no-history control stays flat, then history is not compiling into skill and this part of the design fails.
