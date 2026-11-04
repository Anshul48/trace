<!-- SPDX-License-Identifier: Apache-2.0 -->
# Reflex: an AI that finds the right button

Reflex is a line of work where an AI looks at a screen and finds the right button to press. The direction is SAM 3.1 with Muse Spark.

## The early trial

Everything below is an early trial, a direction: small made-up screens, a handful of runs, not a finished result. A box counted as found when it overlapped the marked one by at least half.

- **Cutting the screen into pieces.** SAM 3.1, called through the Meta Model API, was shown 12 made-up screenshots with 69 marked boxes. Asked with seven phrases together, it found 65 of the 69 (it proposed 85 boxes to find those 65). A second run found 61 of 72. Exploratory, not a controlled comparison.
- **Reading alone.** Muse Spark vision, asked to find the boxes by itself, found 14 of the 69; an agentic variant found 16.
- **The chain.** SAM 3.1 proposed regions and Muse Spark chose among them. Over three sets of 20 made-up tasks, the chain picked right 12, 16 and 16 times; Muse Spark alone picked right 5, 3 and 3 times. The first set's setup was picked after a first look; the other two were fresh.
- **Voice.** Muse voice transcribed 20 short clips per set, exactly right 15, 14 and 13 times.
- **Pictures.** Muse Spark wrote a scene, Muse Image drew it, SAM 3.1 marked it, Muse Spark read it back: 3 of 3 runs completed, with no accuracy claim since there was nothing to score against.

## Watch it

- [Open the replay demo](https://anshul48.github.io/demo-trace-anima-reflex/): no login, pick a Reflex sample.
- [Watch the short film](https://anshul48.github.io/trace/demos/#reflex) (2:06, the owner-approved v3 cut).

Reflex is one of three projects by one builder. [The ecosystem](../README.md#the-ecosystem): TRACE is the memory at the front, ANIMA and Reflex stand behind it.
