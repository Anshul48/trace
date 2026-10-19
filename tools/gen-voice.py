#!/usr/bin/env python3
"""Generate per-scene Kokoro voice-over WAVs + timings.json from narration.md.

STATUS: smoke-tested on the audition path (--audition). Full --script path is
implemented but UNRUN — it needs a real narration.md with per-scene lines,
which is BLOCKED on the missing ws0 scene plan (see TOOLING.md §5).

Environment (exact):
  export LD_LIBRARY_PATH=/tmp/tools/ffmpeg-ex/usr/lib/x86_64-linux-gnu
  export ESPEAK_DATA_PATH=/tmp/tools/ffmpeg-ex/usr/lib/x86_64-linux-gnu/espeak-ng-data
  export PATH=/tmp/tools/ffmpeg-ex/usr/bin:$PATH
  PY=/tmp/venvs/tts/bin/python   # has kokoro_onnx
  MODEL=/tmp/models/kokoro/model.onnx VOICES=/tmp/models/kokoro/voices-v1.0.bin

Usage:
  $PY tools-gen-voice.py --audition [--outdir /tmp/r2/media]
      # renders the fixed audition sentence with af_heart/af_bella/am_adam
  $PY tools-gen-voice.py --script narration.md --voice af_heart --outdir scenes/
      # narration.md format: one scene per block —
      #   ## <scene-id>
      #   <one or more spoken lines, numbers spelled out, no hex>
      # writes scenes/<scene-id>.wav (24 kHz mono s16) + timings.json:
      #   {"<scene-id>": {"file": ..., "duration_s": ...}, ...}

timings.json durations are measured from the written WAV frames (ground truth
for scene-timing the mux), NOT estimated from text.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import wave
from pathlib import Path

MODEL = "/tmp/models/kokoro/model.onnx"
VOICES = "/tmp/models/kokoro/voices-v1.0.bin"
AUDITION_TEXT = "This is a voice audition for the trace documentary narration."
AUDITION_VOICES = ("af_heart", "af_bella", "am_adam")


def write_wav(path: Path, samples, sr: int) -> float:
    import numpy as np

    pcm = (np.asarray(samples) * 32767).astype("<i2").tobytes()
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        w.writeframes(pcm)
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def parse_script(path: Path) -> list[tuple[str, str]]:
    scenes: list[tuple[str, str]] = []
    cur_id: str | None = None
    cur_lines: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"##\s+(\S+)", line)
        if m:
            if cur_id is not None:
                scenes.append((cur_id, " ".join(cur_lines).strip()))
            cur_id, cur_lines = m.group(1), []
        elif line.strip():
            cur_lines.append(line.strip())
    if cur_id is not None:
        scenes.append((cur_id, " ".join(cur_lines).strip()))
    scenes = [(sid, t) for sid, t in scenes if t]
    if not scenes:
        raise ValueError(f"no scenes parsed from {path}")
    return scenes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audition", action="store_true")
    ap.add_argument("--script", default=None)
    ap.add_argument("--voice", default="af_heart")
    ap.add_argument("--lang", default="en-us")
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()

    from kokoro_onnx import Kokoro

    k = Kokoro(MODEL, VOICES)
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)

    if args.audition:
        for v in AUDITION_VOICES:
            samples, sr = k.create(AUDITION_TEXT, voice=v, lang=args.lang)
            p = outdir / f"audition-{v}.wav"
            dur = write_wav(p, samples, sr)
            print(f"{v}: {p} sr={sr} dur={dur:.1f}s")
        return 0

    if not args.script:
        ap.error("--script narration.md is required without --audition")
    timings: dict[str, dict] = {}
    for sid, text in parse_script(Path(args.script)):
        samples, sr = k.create(text, voice=args.voice, lang=args.lang)
        p = outdir / f"{sid}.wav"
        dur = write_wav(p, samples, sr)
        timings[sid] = {"file": str(p), "duration_s": round(dur, 2)}
        print(f"{sid}: dur={dur:.2f}s")
    tp = outdir / "timings.json"
    tp.write_text(json.dumps(timings, indent=2), encoding="utf-8")
    print(f"wrote {tp} ({len(timings)} scenes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
