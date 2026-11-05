# 60-second tour storyboards (silent)

Two silent films, 1920x1080, light theme, fresh browser storage, no audio.
Each is six scenes of ten seconds, so each runs 60 seconds and the pair runs 120 seconds.
Captions are burned in by the recorder as a white bar with ink text and a blue edge, at most 12 words per screen.
Both films use only recorded, built pages. The recorders are `tools/record_tour.py` (TRACE, this repo) and `tools/record_demo.py` (ANIMA repo, `anima-substrate`).

Re-record: `python3 tools/record_tour.py` writes `docs/media/tour-60s.mp4` and `docs/media/tour-60s.png`.

## Part 1. TRACE explorer tour (file: `tour-60s.mp4`)

| # | Time | Shot | On-screen action | Caption |
|---|------|------|------------------|---------|
| 1 | 0:00-0:10 | Home page, top of page | Page loads, slow scroll down past the opening, back to the top where the one primary button sits | TRACE: search you can check, shown on recorded questions. |
| 2 | 0:10-0:20 | Explorer opens | Click "Open the explorer"; the explorer loads; page scrolls to the question box and the list of recorded questions | The explorer replays real searches recorded on a sealed library. |
| 3 | 0:20-0:30 | Recorded question list | Hover the first recorded question, click it; ranked passages appear | Pick a recorded question. Results are replayed, not live. |
| 4 | 0:30-0:40 | Ranked result cards | Scroll to the first result card, click "See its checkable record"; the record opens | Open any result to see where it came from. |
| 5 | 0:40-0:50 | Checkable record | Scroll to the record facts (article, position, licence, stored fingerprint); click "Check the fingerprint in my browser"; a match message appears | Your browser re-checks the stored fingerprint against the text. |
| 6 | 0:50-1:00 | "What this shows, and what it does not" | Scroll to the limits section; slow scroll through the two columns | Honest limits: a replay only, and the public search is off. |

## Part 2. ANIMA recorded replay (file: `replay-60s.mp4`, in the `anima-substrate` repo)

| # | Time | Shot | On-screen action | Caption |
|---|------|------|------------------|---------|
| 7 | 0:00-0:10 | Demo page "Check ANIMA's record" | Page loads; the nine-job table fills; slow scroll to "The nine jobs" | ANIMA: a prototype for one job type, fixing a bug. |
| 8 | 0:10-0:20 | UI preview, state tree screen | Open the UI preview, set speed to 2x, press Play; the nine jobs fill in as the recorded run replays | A recorded replay of nine bug-fixing jobs. |
| 9 | 0:20-0:30 | Demo page, summary tiles and job table | Scroll to the summary tiles, then the job table: jobs where the worker said done and the hidden checker said no | The hidden checker catches a worker's wrong "done". |
| 10 | 0:30-0:40 | Demo page "Check the record" | Press "Check the record" (chain verifies in the browser), then "Change one character"; the check now fails | Change one character and the record check fails. |
| 11 | 0:40-0:50 | UI preview, state tree at end of run | Drag to the last record so the full tree shows; click an escalated task to show its attempts | The state tree shows every task and attempt. |
| 12 | 0:50-1:00 | UI preview label | Hold on the "UI preview" tag (outlined in blue) and the "replay of a recorded run, not live" header | UI preview: a recorded replay, not a live run. |

## Checks applied to this file

- 12 scenes, 12 x 10 s = 120 s total (limit: 120 s).
- Every caption is 12 words or fewer.
- No performance numerals appear in any caption; no scope-bound figure is used, so none needs a scope line.
- The banned-word grep from the house rules returns nothing on this file.
- Mock screens carry "UI preview" and replays carry "recorded replay" on screen.
- ANIMA is shown only as a prototype for one job type. No unbuilt feature is shown as working.
