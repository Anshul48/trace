<!-- SPDX-License-Identifier: Apache-2.0 -->
# The top-down guess: placing new pieces cheaply, learning from the miss

**FOR A NEW READER.** Grouping every new piece from scratch is expensive, so the design adds a cheap guess: before placing a piece, predict which groups it will land in from its neighbours and context. The grouping then starts from the guess and only checks the nearby groups. Where the guess keeps missing, the miss itself rebuilds that region of the grouping.

## What exists today

DESIGN. The guesser and the miss-driven rebuild do not run anywhere. The idea was tried on a made-up test set with known groups and came in below its bar.

## Latest measured number

On 9 November, on a made-up test set with known groups (development runs; one seed independently rerun): starting from the guess saved 26 to 30 percent of the distance checks per piece against a 40 percent bar, and grouping quality was not hurt. On the one seed that was rerun independently: 39.9 checks per piece with the guess, 56.6 without. The comparison that mattered failed: a plain guesser saved as much as the context-aware one, so learned context is not shown to save any work. Context only won on guess accuracy (0.27 against 0.17). Baselines: unaided grouping, and the plain guesser beside the context-aware one.

## What it does not show

It does not show the 40 percent saving the design asks for, it does not show a context-aware guesser beating a plain one on cost, and it does not show misses rebuilding any region: all of that ran on the made-up test set only.

## What would prove it wrong

If the guess never reaches its saving bar without hurting grouping quality, or if regions with persistent misses cannot be rebuilt from the miss signal, the top-down half of the design fails and grouping stays bottom-up only.
