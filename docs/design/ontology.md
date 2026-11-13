<!-- SPDX-License-Identifier: Apache-2.0 -->
# The grouping: an outline that builds and rebuilds itself

**FOR A NEW READER.** The design: TRACE would keep its text in a grouping shaped like an outline. Small pieces of meaning would gather into groups, groups into bigger groups, and every piece would keep its link back to the raw text it came from. The same piece could sit in more than one group, and use would reshape the grouping: pieces used together would move together. No person would write or maintain this outline; the store would build it from the material. None of this runs today.

## What exists today

DESIGN. The full structure above does not run anywhere. One piece of it is EXPERIMENTAL: a program that groups code into modules without being told how many groups there are (see `organiser.md`).

## Latest measured number

The only measured piece is the organiser: 0.27 against 0.30 for k-means told the number of groups, on Python standard-library code. Details and limits: [organiser.md](organiser.md).

## What it does not show

It does not show a whole outline, only the bottom level of one. It does not show grouping that improves with use, pieces shared between groups, or anything at the size of the full library. It does not show the grouping surviving new material arriving over time.

## What would prove it wrong

If the grouping never beats the told-count baseline on real material, or if new material collapses the groups it already built, the design as written fails and goes back to the drawing board.
