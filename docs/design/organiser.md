<!-- SPDX-License-Identifier: Apache-2.0 -->
# The organiser: grouping without being told how many groups

**FOR A NEW READER.** When new material arrives, something must decide where it goes in the grouping. The organiser does that job from the bottom up: it compares each new piece with the groups that exist, joins the close ones, and starts a new group when nothing is close enough. Nobody tells it the number of groups in advance.

## What exists today

EXPERIMENTAL. A first version runs on real code and is scored against the true module layout. It is not part of any served store.

## Latest measured number

On 12 November, on real code (Python standard library, 180 functions per draw, 5 draws, sentence-embedding vectors): grouping functions by module without being told the number of groups, it scored 0.27 (adjusted Rand index: 1 is identical groupings, 0 is chance) against 0.30 for k-means told the number of groups. It did not beat that baseline, and it made 18 to 23 groups where there are 12 modules. Development data only; no held-out test.

## What it does not show

It does not show grouping that holds up over long streams of new material, grouping at the size of the full library, or shared pieces between groups. The runnable copy in this repo ([experiments/organiser-on-code](../../experiments/organiser-on-code/)) scores 0.23 against 0.25 for k-means with word-count vectors built by Python alone (TF-IDF). The 0.27 against 0.30 above used sentence-embedding vectors from a file that is not published yet. Above the first level, a single cut has failed under five different rules. Scored as a whole tree, a streamed build was worse than a batch build (0.51 against 0.66 on task cards; 0.20 against 0.94 on one store). On our own store, the first level lands at the scale of the hand-set leaves (agreement 0.59 on 15 fresh slices), and the hand-set leaves are somewhat better by document: it is not a replacement for them. (As reported by the builders, not yet rerun.)

## What would prove it wrong

If it never matches the told-count baseline on real material, or if its groups churn without settling as new material arrives, this approach to grouping fails and the design must change.
