"""P8 startup preflight (fail-closed). Runs before P4 acquire at every startup.
FAIL blocks serving (commits AND queries). No skip flag.
"""
import fcntl
import os
import sqlite3
import struct
import time

SUSPECT_FS = {
    # statfs magic -> (name, remedy)
    0x01021997: ("9P", "reroute the store to native storage"),
    0x6969: ("NFS?", None),  # not suspect by itself; kept for record clarity
}
# DrvFS has no stable public statfs magic from inside WSL; detect by
# filesystem type string via /proc/mounts device fstype fields instead.
SUSPECT_FSTYPES = ("9p", "drvfs", "plan9")


def _statfs_type(path):
    import ctypes
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    buf = ctypes.create_string_buffer(120)  # struct statfs; f_type is first long
    if libc.statfs(path.encode(), buf) != 0:
        raise OSError(ctypes.get_errno(), "statfs failed")
    return ctypes.cast(buf, ctypes.POINTER(ctypes.c_long)).contents.value


def _fstype_from_mounts(path):
    rp = os.path.realpath(path)
    best = (None, None)
    try:
        with open("/proc/mounts") as f:
            for line in f:
                parts = line.split()
                if len(parts) < 3:
                    continue
                dev, mnt, fst = parts[0], parts[1], parts[2]
                if rp == mnt or rp.startswith(mnt.rstrip("/") + "/"):
                    if best[0] is None or len(mnt) > len(best[0]):
                        best = (mnt, fst)
    except OSError:
        return None
    return best[1]


def check_transport(store_root):
    """P8 step 3: ONE UNAMBIGUOUS RULE. Returns (fstype, verdict, reason)."""
    fst = _fstype_from_mounts(store_root)
    mag = _statfs_type(store_root)
    if fst is not None and fst.lower() in SUSPECT_FSTYPES:
        return (fst, "FAIL", f"suspect transport {fst}: reroute the store to "
                "native storage (P8 strict refusal; probes never redeem it)")
    if mag in SUSPECT_FS and SUSPECT_FS[mag][1]:
        name, remedy = SUSPECT_FS[mag]
        return (fst or hex(mag), "FAIL", f"suspect transport {name}: {remedy}")
    return (fst or hex(mag), "PASS", "native")


def check_ofd_exclusion(tmpdir):
    """P8 step 1: two descriptions, mutual exclusion must hold."""
    p = os.path.join(tmpdir, "preflight-ofd-probe")
    fd1 = os.open(p, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
    fd2 = os.open(p, os.O_RDWR | os.O_CLOEXEC)
    try:
        lk = struct.pack("hhqqih", fcntl.F_WRLCK, 0, 0, 0, 0, 0)
        fcntl.fcntl(fd1, fcntl.F_OFD_SETLK, lk)
        try:
            fcntl.fcntl(fd2, fcntl.F_OFD_SETLK, lk)
            return ("FAIL", "OFD lock did not exclude: absent semantics")
        except OSError:
            return ("PASS", "mutual exclusion holds")
        finally:
            fcntl.fcntl(fd1, fcntl.F_OFD_SETLK,
                        struct.pack("hhqqih", fcntl.F_UNLCK, 0, 0, 0, 0, 0))
    except (OSError, AttributeError) as e:
        return ("FAIL", f"OFD unavailable: {e}")
    finally:
        os.close(fd1)
        os.close(fd2)
        try:
            os.remove(p)
        except OSError:
            pass


def check_fsync_canary(tmpdir):
    """P8 step 2: canary + fdatasync + dir-fsync + readback."""
    p = os.path.join(tmpdir, "preflight-fsync-probe")
    canary = b"tl-stage-a-canary-" + str(time.time()).encode()
    try:
        fd = os.open(p, os.O_RDWR | os.O_CREAT | os.O_CLOEXEC, 0o644)
        try:
            os.write(fd, canary)
            os.fdatasync(fd)
        finally:
            os.close(fd)
        dfd = os.open(tmpdir, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
        with open(p, "rb") as f:
            back = f.read()
        if back != canary:
            return ("FAIL", "canary mismatch")
        return ("PASS", "call path works (not power-loss proof)")
    except OSError as e:
        return ("FAIL", f"fsync path error: {e}")
    finally:
        try:
            os.remove(p)
        except OSError:
            pass


def check_shm():
    """P8 step 4: substrate exists at all."""
    try:
        from multiprocessing import shared_memory
        s = shared_memory.SharedMemory(create=True, size=64)
        s.close()
        s.unlink()
        return ("PASS", "posix shm create/map/unlink ok")
    except Exception as e:
        return ("FAIL", f"no shared-state substrate: {e}")


def check_db(db_path):
    """P8 step 5: open + epoch row + lock identity + integrity."""
    try:
        con = sqlite3.connect(db_path, timeout=10)
    except Exception as e:
        return ("FAIL", f"db open failed: {e}")
    try:
        q = con.execute("PRAGMA quick_check;").fetchone()
        if q is None or q[0] != "ok":
            return ("FAIL", f"integrity: {q}")
        erow = con.execute("SELECT birth,epoch FROM epoch_row").fetchone()
        if erow is None:
            return ("FAIL", "epoch row missing")
        lr = con.execute("SELECT COUNT(*) FROM meta WHERE k IN ('lock_dev','lock_ino')").fetchone()
        if lr[0] != 2:
            return ("FAIL", "lock-identity record incomplete")
        return ("PASS", "open + epoch row + lock identity + quick_check ok")
    except Exception as e:
        return ("FAIL", f"db check error: {e}")
    finally:
        con.close()


def check_accounting_bootstrap(store_root, db_path):
    """P8 step 6: WAL/retained sizes readable."""
    try:
        os.path.getsize(db_path)
        wal = db_path + "-wal"
        if os.path.exists(wal):
            os.path.getsize(wal)
        return ("PASS", "sizes readable")
    except OSError as e:
        return ("FAIL", f"unmeasurable: {e}")


def run(store_root, db_path, tmpdir):
    """Full P8 sequence. Returns dict; any FAIL => overall FAIL (no serving)."""
    t0 = time.time()
    results = {}
    results["ofd"] = check_ofd_exclusion(tmpdir)
    results["fsync"] = check_fsync_canary(tmpdir)
    fstype, tv, tr = check_transport(store_root)
    results["transport"] = (tv, f"{fstype}: {tr}")
    results["shm"] = check_shm()
    results["db"] = check_db(db_path)
    results["accounting"] = check_accounting_bootstrap(store_root, db_path)
    overall = "PASS" if all(v == "PASS" for v, _ in results.values()) else "FAIL"
    return {"verdict": overall, "results": results,
            "elapsed_s": round(time.time() - t0, 3)}
