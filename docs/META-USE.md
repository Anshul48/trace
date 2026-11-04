# Which Meta products and models we used, and which we did not

This page is for judges of the Meta hackathon. It lists, one line each, what we really used, what we did not use, and what we could not confirm. It was written from a read-only check of our own work logs on 4 November 2026. Nothing here goes beyond that check.

The short version:

- **Muse Code** with the model **muse-spark-1.3** was our main automated worker tool: 670 recorded jobs on two machines.
- **TRACE's search itself uses no Meta model.** Its text encoder is all-MiniLM-L6-v2, which is not from Meta. PyTorch, an open-source library created at Meta, ran the encoding of the library.
- We called **SAM 3.1, Muse Spark vision, Muse voice and Muse Image** in small, recorded, exploratory experiments on synthetic screenshots, for a separate project (Reflex).
- We found **no Llama or other Meta open-weights model** anywhere in our code.

Back to the [TRACE home page](https://anshul48.github.io/trace/) or the [README](../README.md).

## Used, not used, and unconfirmed

| Item | Status | What the records show |
|---|---|---|
| Muse Code command-line tool, version 1.4.14 | Used | It prints "Muse Code 1.4.14". Its default provider is `meta`. Its non-interactive mode ("exec") ran our worker jobs. |
| Muse Code as the automated worker, on the laptop | Used, large | 396 readable job records: 357 done, 22 failed, 9 cancelled, 8 still running when we counted. 503 attempts, about 127 hours of summed attempt time (jobs ran in parallel, so this is not wall-clock time). 1 to 4 November 2026. The model is named `muse-spark-1.3` on 394 jobs and `muse-wonder-1.0` on 2. |
| The same, on a cloud machine | Used | 274 job records: 262 done, 12 cancelled, 0 failed. All name `muse-spark-1.3`. About 43 hours of summed attempt time. |
| Combined worker totals | Used | 670 jobs (396 on the laptop, 274 on the cloud machine); 619 done, 22 failed, 21 cancelled, 8 running when we counted. About 170 hours of summed attempt time. 778 attempts: 695 on Muse subscription accounts, 82 on a Meta API key, 1 on Claude. |
| What the workers did | Used | Job names show work on TRACE (for example 32 of 33 done), ANIMA, Reflex, film production, restores, documentation and tests. Each job had a written brief and a result file, and the architect (Claude) and the owner reviewed the results. One example with a written record: a worker job encoded the 812,545-passage library on the laptop's graphics card in 1,002.6 seconds. |
| Muse as a builder inside the TRACE repository | Used, partial | `freeze-src/BUILD-REPORT.md` in this repository says "Builder: Muse (subagent)" for the fixes to the frozen engine fork, 12 to 13 October 2026. None of the 145 commit messages mention Muse, so the git history alone does not show it. We do not claim a share of TRACE was written by Muse. |
| ANIMA's Muse Code adapter | Used | ANIMA (our companion project) treats Muse Code as a harness next to Claude Code and Codex. Its adapter passes 39 tests, which use a stand-in program instead of the real tool. |
| ANIMA's first rung is a Muse Code worker | Used | In two recorded ANIMA runs, the first rung of the helper ladder was a Muse Code worker on the laptop. 16 of 18 jobs were verified on the first try, and 2 wrong "done" answers were caught. This is one kind of job (fixing a bug against hidden tests). |
| SAM 3.1 through the Meta Model API | Used, small | A Reflex research experiment on 12 synthetic screenshots with 69 labelled boxes: 96 calls, none failed. Combining 7 phrases found 65 of 69 boxes at an overlap of 0.5, with 85 boxes drawn. A second seed found 61 of 72. An independent re-score reproduced the first result. Exploratory, not a controlled comparison. |
| Muse Spark vision (image input to `muse exec`) | Used, small | On the same 12 images: 14 of 69 boxes (20.3%), and 16 of 69 (23.2%) for an agentic variant. |
| SAM then Muse Spark, as a chain | Used, small | Three seeds of 20 synthetic tasks: the chain was right in 12, 16 and 16 of 20, against 5, 3 and 3 of 20 for Muse Spark alone. Small, synthetic, exploratory. |
| Muse voice (speech to text) | Used, small | An exact transcript in 15, 14 and 13 of 20 synthetic clips over three seeds. |
| Muse Image | Used, small | Muse Spark text, then Muse Image, then SAM 3.1, then Muse Spark vision: 3 of 3 runs completed, images of 1920 by 1280 pixels, 36 of 36 marks labelled. No ground truth, so no accuracy claim. |
| Muse Wonder 1.0 | Used, trivial | Two jobs (one smoke test done, one cancelled). Not material. |
| PyTorch (created at Meta, now governed by the PyTorch Foundation) | Used | It ran the GPU encoding of the 812,545-passage library (torch 2.11.0 on a laptop GPU). It also ran a side experiment on three small public sets. |
| FAISS (open source from Meta) | Used, side experiment only | Used as a cross-check in a side experiment on three small public sets. It is not in TRACE and not in this repository. |
| TRACE's text encoder | Not Meta | all-MiniLM-L6-v2 (sentence-transformers). |
| Any Meta model inside TRACE's search path | Not used | TRACE declares no runtime dependencies beyond numpy and blake3, and no language model appears in its search path. We did not check which library the live service uses to encode a question, so we do not say that PyTorch is absent at question time. |
| Llama or any Meta open-weights model | Not used | No import or dependency in the TRACE or ANIMA code or documents. |
| Whisper in ANIMA's voice feature | Not Meta | The log says "whisper base on CPU". |
| Glimmer | Not used | It appears only as a name in a notes file, with its abilities marked unverified. |
| The model family behind muse-spark-1.3 | Unknown | The files name only the catalog id and the provider `meta`. We do not say what it is built on, and we do not say whether it is open-weights. |
| ANIMA's real Muse Code run time on a fresh clone | Unconfirmed | A figure had been reported but its record was not on disk when we checked. We do not state it. |
| The model behind ANIMA's 18 first-rung jobs | Unconfirmed | The job records were on a disk that was lost. "Muse Code worker" is proven; "muse-spark-1.3" is inferred, so we say "Muse Code". |
| The vision model in the Reflex film | Unconfirmed | The Reflex notes name no model. We do not say that Reflex runs on Muse Spark or SAM. |

## What we do not claim

- Nothing about Llama, "built on Meta's open models", or what family the Muse models belong to.
- That TRACE uses, is powered by, or retrieves with a Meta model. It does not.
- That Muse wrote TRACE, or any share of its code. The architect layer was Claude plus the owner.
- That Muse is cheaper, faster or better than any other tool. We ran no like-for-like cost or quality comparison.
- That SAM beats Muse Spark. The comparison depends on how each was set up: Muse Spark was asked to find all seven classes in one pass, while SAM got seven separate phrases.
- Any SAM or Muse Image result as a headline accuracy number. They are synthetic, 12 or 20 items, and not controlled.

## How this was checked, and its limits

Read-only: job records (counts only), the tool's help and version output, scoped searches of the TRACE and ANIMA code, the written records of the Reflex experiments, and one read-only count on the cloud machine's job ledger. No secret file was opened. The numbers come from our own logs and no outside party has verified them. The page is a snapshot: the job counts were taken on 4 November 2026 while some jobs were still running.
