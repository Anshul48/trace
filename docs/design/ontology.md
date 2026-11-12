<!-- SPDX-License-Identifier: Apache-2.0 -->
# The grouping: an outline that builds and rebuilds itself

**FOR A NEW READER.** TRACE keeps knowledge in a grouping shaped like an outline: small pieces of meaning gather into groups, groups gather into bigger groups, and every piece keeps its links back down to the raw text it came from. The same piece may sit in more than one group, and using the store reshapes the grouping: pieces used together move together. No person writes or maintains this outline; the store builds it from the material itself.

## What exists today

DESIGN. The full structure above does not run anywhere. One piece of it is EXPERIMENTAL: a program that groups code into modules without being told how many groups there are (see `organiser.md`).

## Latest measured number

On 12 November, on real code (180 functions per draw, 5 draws), the grouping program scored 0.27, where the score is 1 for groupings identical to the true modules and 0 for chance. Beside it, the standard method told the true number of groups scored 0.30. The new program did not beat that baseline, and it made 18 to 23 groups where there are 12 modules. Development data only; no held-out test.

## What it does not show

It does not show a whole outline, only the bottom level of one. It does not show grouping that improves with use, pieces shared between groups, or anything at the size of the full library. It does not show the grouping surviving new material arriving over time.

## What would prove it wrong

If the grouping never beats the told-count baseline on real material, or if new material collapses the groups it already built, the design as written fails and goes back to the drawing board.
