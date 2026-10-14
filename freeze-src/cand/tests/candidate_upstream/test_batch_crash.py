#!/usr/bin/env python3
"""T3 batch crash (kill -9) invariant testing on the ACTUAL candidate.

Loop (3 kill cycles, different seeded sleeps): a child process drives
K=60 batches of 10 serial EDITs on a fresh store; the parent sleeps a
random 0.2-2.0 s then kill -9s the child. The parent then (fresh conns):
  (i)   committed seqs are gapless 1..M for some M (any M);
  (ii)  ATOMICITY: every batch (grouped by sidecar line; the child
        appends+fsyncs one 10-id line per batch BEFORE each commit_batch)
        is ALL committed or ALL absent -- NO mixed batch;
  (iii) re-drive ALL unacked op_ids via commit_batch -> final state: all
        600 committed, gapless, no dup rows (COUNT==600, dedup rows for
        the crash ids == 600).
Any mixed batch, dup, or gap -> FAIL.

Plan/sidecar note (spec deviation, deliberate): the parent mints the
full 600-id plan upfront (seeded) so "all 600 committed" is well-defined
even when the child is killed early; the sidecar covers submitted
batches only. The re-drive set is plan-minus-committed, which always
covers sidecar-minus-committed (asserted).

Usage: python3 test_batch_crash.py --sut <dir> --store-root <dir>
Exit 0 PASS, 1 FAIL, 2 BLOCKED. Stdlib only. Zero harness imports.
"""
import argparse
import os
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True

K_BATCHES = 60
BATCH = 10
N_OPS = K_BATCHES * BATCH


def mint_v7(ts_ms, ra, rb):
    v = ((ts_ms & 0xFFFFFFFFFFFF) << 80) | (7 << 76) | ((ra & 0xFFF) << 64) | (2 << 62) | (rb & 0x3FFFFFFFFFFFFFFF)
    h = "%032x" % v
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


def child_main(sut, store_dir, plan_path, sidecar_path):
    sys.path.insert(0, os.path.abspath(sut))
    from store import Store, Fence
    from committer import Committer
    if not hasattr(Committer, "commit_batch"):
        print("CHILD BLOCKED: Committer.commit_batch missing")
        return 2
    with open(plan_path) as f:
        batches = [ln.split() for ln in f if ln.strip()]
    assert len(batches) == K_BATCHES and all(len(b) == BATCH for b in batches), "plan shape"
    store = Store(store_dir)  # open existing; parent created it
    fence = Fence(store)
    fence.acquire()
    try:
        cm = Committer(store, fence)
        with open(sidecar_path, "a") as sc:
            for bi, ids in enumerate(batches):
                # sidecar append + fsync BEFORE the commit_batch call
                sc.write(" ".join(ids) + "\n")
                sc.flush()
                os.fsync(sc.fileno())
                ops = [{"op_id": o, "kind": "EDIT",
                        "payload": {"body": f"crash-b{bi}-o{oi}:{o}"},
                        "disclosure": {"leg": "t3"}, "approval_ref": None,
                        "artifacts": ()}
                       for oi, o in enumerate(ids)]
                results, _info = cm.commit_batch(ops)
                for r in results:
                    if r.get("status") != "committed":
                        print(f"CHILD FAIL: batch {bi} status {r.get('status')}")
                        return 1
    finally:
        fence.release()
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sut", required=True)
    ap.add_argument("--store-root", required=True)
    ap.add_argument("--child", action="store_true")
    ap.add_argument("--store-dir", default=None)
    ap.add_argument("--plan", default=None)
    ap.add_argument("--sidecar", default=None)
    args = ap.parse_args()
    if args.child:
        return child_main(args.sut, args.store_dir, args.plan, args.sidecar)

    sut = os.path.abspath(args.sut)
    for m in ("store.py", "committer.py", "intake.py", "replay.py"):
        if not os.path.isfile(os.path.join(sut, m)):
            print("BLOCKED: SUT missing", m)
            print("RESULT: BLOCKED [sut-missing]")
            return 2
    sys.path.insert(0, sut)
    from store import Store, Fence
    from committer import Committer

    import random as _r
    root = os.path.join(os.path.abspath(args.store_root),
                        "t3-crash-%d-%d-%04x" % (os.getpid(), int(time.time()), _r.randrange(65536)))
    os.makedirs(root, exist_ok=False)

    fails, blocked = [], []

    def check(name, cond, detail=""):
        print(("PASS " if cond else "FAIL ") + name + ("" if cond else f" :: {detail}"))
        if not cond:
            fails.append(name)

    def block(name, detail=""):
        print("BLOCKED " + name + ("" if not detail else f" :: {detail}"))
        blocked.append(name)

    if not hasattr(Committer, "commit_batch"):
        block("api-commit_batch-missing",
              "Committer has no attribute commit_batch (SUT=" + sut + ")")
        print("RESULT:", "BLOCKED" if not fails else f"FAIL {fails}", blocked)
        return 2

    sleeps = [_r.Random(2026092803 + c).uniform(0.2, 2.0) for c in range(3)]
    check("sleeps-distinct", len(set(round(s, 6) for s in sleeps)) == 3, f"{sleeps}")

    for cyc in range(3):
        tag = f"c{cyc}"
        cdir = os.path.join(root, f"cycle{cyc}")
        os.makedirs(cdir, exist_ok=False)
        sdir = os.path.join(cdir, "store")
        Store.create(sdir)  # parent creates; child only opens (no fence held here)
        rng = _r.Random(2026092900 + cyc)
        now_ms = int(time.time() * 1000)
        plan = [[mint_v7(now_ms + bi * BATCH + oi, rng.getrandbits(12), rng.getrandbits(62))
                 for oi in range(BATCH)] for bi in range(K_BATCHES)]
        plan_path = os.path.join(cdir, "plan.txt")
        with open(plan_path, "w") as f:
            for ids in plan:
                f.write(" ".join(ids) + "\n")
        sidecar = os.path.join(cdir, "sidecar.txt")
        open(sidecar, "w").close()
        all_ids = [o for ids in plan for o in ids]

        proc = subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--sut", sut,
             "--store-root", root, "--child", "--store-dir", sdir,
             "--plan", plan_path, "--sidecar", sidecar],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        time.sleep(sleeps[cyc])
        alive_at_kill = proc.poll() is None
        if alive_at_kill:
            proc.send_signal(signal.SIGKILL)
        try:
            out, _ = proc.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            proc.kill()
            out, _ = proc.communicate(timeout=30)
        print(f"INFO {tag}: sleep={sleeps[cyc]:.2f}s alive_at_kill={alive_at_kill} "
              f"rc={proc.returncode} child_out={out.strip()[:120]!r}")
        if proc.returncode == 0:
            pass  # child finished before the kill: checks below still apply
        elif alive_at_kill and proc.returncode == -signal.SIGKILL:
            pass  # expected kill
        else:
            check(f"{tag}-child-exit", False,
                  f"rc={proc.returncode} alive={alive_at_kill} out={out.strip()[:200]!r}")
            continue

        store = Store(sdir)
        # ---- (i) gapless 1..M ----
        con = store.open_db()
        try:
            seqs = [r[0] for r in con.execute("SELECT seq FROM commits ORDER BY seq").fetchall()]
            committed_ids = set(r[0] for r in con.execute("SELECT op_id FROM commits").fetchall())
        finally:
            con.close()
        m = len(seqs)
        print(f"INFO {tag}: M={m} committed_at_kill")
        check(f"{tag}-gapless", seqs == list(range(1, m + 1)),
              f"M={m} head={seqs[:5]} tail={seqs[-5:] if seqs else []}")
        check(f"{tag}-batch-multiple", m % BATCH == 0, f"M={m}")

        # ---- (ii) atomicity over sidecar batches ----
        with open(sidecar) as f:
            lines = [ln.split() for ln in f if ln.strip()]
        torn = [ln for ln in lines if len(ln) != BATCH]
        if torn:
            print(f"INFO {tag}: dropping {len(torn)} torn sidecar line(s)")
        batches_seen = [ln for ln in lines if len(ln) == BATCH]
        mixed = []
        for ln in batches_seen:
            n = sum(1 for o in ln if o in committed_ids)
            if n not in (0, BATCH):
                mixed.append((ln[0][:8], n))
        check(f"{tag}-no-mixed-batch", not mixed,
              f"mixed={mixed[:5]} sidecar_batches={len(batches_seen)}")

        # ---- (iii) re-drive unacked, final all-600 ----
        sidecar_ids = set(o for ln in batches_seen for o in ln)
        sidecar_unacked = sidecar_ids - committed_ids
        redrive = [o for o in all_ids if o not in committed_ids]
        check(f"{tag}-sidecar-covered", sidecar_unacked <= set(redrive),
              f"sidecar_unacked={len(sidecar_unacked)} redrive={len(redrive)}")
        fence = Fence(store)
        try:
            fence.acquire()
        except Exception as e:
            check(f"{tag}-fence-reacquire", False, f"{type(e).__name__}: {e}")
            continue
        check(f"{tag}-fence-reacquire", True)
        try:
            cm = Committer(store, fence)
            redrive_ok = True
            for i in range(0, len(redrive), BATCH):
                grp = redrive[i:i + BATCH]
                # payloads must match the plan's originals (id-stable re-drive)
                ops = [{"op_id": o, "kind": "EDIT",
                        "payload": {"body": f"crash-b{all_ids.index(o) // BATCH}"
                                           f"-o{all_ids.index(o) % BATCH}:{o}"},
                        "disclosure": {"leg": "t3"}, "approval_ref": None,
                        "artifacts": ()} for o in grp]
                try:
                    results, _info = cm.commit_batch(ops)
                except Exception as e:
                    check(f"{tag}-redrive-call", False, f"{type(e).__name__}: {e}")
                    redrive_ok = False
                    break
                bad = [r for r in results if r.get("status") != "committed"]
                if bad:
                    check(f"{tag}-redrive-call", False, f"bad={str(bad[0])[:150]}")
                    redrive_ok = False
                    break
            if redrive_ok:
                check(f"{tag}-redrive-call", True)
            con = store.open_db()
            try:
                n = con.execute("SELECT COUNT(*) FROM commits").fetchone()[0]
                seqs2 = [r[0] for r in con.execute("SELECT seq FROM commits ORDER BY seq").fetchall()]
                dd = con.execute("SELECT COUNT(*) FROM dedup WHERE op_id IN (%s)"
                                 % ",".join("?" * len(all_ids)), all_ids).fetchone()[0]
                # no dup rows: distinct op_ids in commits == COUNT
                distinct = con.execute("SELECT COUNT(DISTINCT op_id) FROM commits").fetchone()[0]
            finally:
                con.close()
            check(f"{tag}-final-600", n == N_OPS, f"COUNT={n}")
            check(f"{tag}-final-gapless", seqs2 == list(range(1, N_OPS + 1)),
                  f"len={len(seqs2)}")
            check(f"{tag}-final-dedup-600", dd == N_OPS, f"dedup={dd}")
            check(f"{tag}-final-no-dup", distinct == n == N_OPS,
                  f"distinct={distinct} n={n}")
        finally:
            fence.release()

    if fails:
        print("RESULT:", f"FAIL {fails}")
        return 1
    if blocked:
        print("RESULT:", f"BLOCKED {blocked}")
        return 2
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
