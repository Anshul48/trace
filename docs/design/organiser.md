<!-- SPDX-License-Identifier: Apache-2.0 -->
# The organiser: grouping without being told how many groups

**FOR A NEW READER.** When new material arrives, something must decide where it goes in the grouping. The organiser does that job from the bottom up: it compares each new piece with the groups that exist, joins the close ones, and starts a new group when nothing is close enough. Nobody tells it the number of groups in advance.

## What exists today

EXPERIMENTAL. A first version runs on real code and is scored against the true module layout. It is not part of any served store.

## Latest measured number

On 12 November, on real code (Python standard library, 180 functions per draw, 5 draws, sentence-embedding vectors): grouping functions by module without being told the number of groups, it scored 0.27 (adjusted Rand index: 1 is identical groupings, 0 is chance) against 0.30 for k-means told the number of groups. It did not beat that baseline, and it made 18 to 23 groups where there are 12 modules. Development data only; no held-out test.

## What it does not show

It does not show grouping that holds up over long streams of new material, grouping at the size of the full library, or shared pieces between groups. The runnable copy in this repo ([experiments/organiser-on-code](../../experiments/organiser-on-code/)) scores 0.23 against 0.25 for k-means with word-count vectors built by Python alone (TF-IDF). The 0.27 against 0.30 above used sentence-embedding vectors from a file that is not published yet. Three more results, as reported by the builders and not yet rerun. The level above: five rules for joining first-level groups into bigger groups were tried and none worked. Order of arrival: when pieces arrive one at a time, the whole outline scores worse than when it is built from all pieces at once (0.51 against 0.66 on a set of our own task notes; 0.20 against 0.94 on one store). On TRACE's own store: the organiser's first-level groups come out about the size of the store's existing hand-tuned groups (agreement 0.59 on 15 fresh samples), and the existing groups are somewhat better when scored by document. The organiser does not replace them.

## What would prove it wrong

If it never matches the told-count baseline on real material, or if its groups churn without settling as new material arrives, this approach to grouping fails and the design must change.
