"""W7 exact-gen cache per S-04 Q1.5/Q1.6 + CACHE-INTERFACE-SPEC (scratch).

Process-local; keys = full generation identity (never bare seq) + query +
complete result-affecting context incl. pinned compatible retrieval config
+ execution-policy config incl. hard ceiling. Completed-only admission:
completed-late eligible (lateness carried); hard-stopped/interrupted
partials never admitted as complete. Eviction: LRU (experimental; LRU-vs-
clock stays open per Q1.5). Owner: S-04/query-path. Assessment records use
the S-02 term with S-02 ownership distinct (recorded_by differs from owner).
"""
import collections
import hashlib
import json
import time

from common import Reject

ASSESS_SCHEMA = """
CREATE TABLE IF NOT EXISTS assessments(assess_id TEXT PRIMARY KEY, term TEXT NOT NULL,
  owner TEXT NOT NULL, recorded_by TEXT NOT NULL, scope TEXT NOT NULL,
  verdict TEXT NOT NULL, detail TEXT NOT NULL, ts REAL NOT NULL);
"""


def canon(o):
    return json.dumps(o, sort_keys=True, separators=(",", ":"))


def make_key(gen_triple, query, retrieval_config, exec_policy):
    """gen_triple: full identity 'birth:epoch:seq' (never bare seq). Returns
    (key_canon, key_digest). The digest covers the full context."""
    if not isinstance(gen_triple, str) or gen_triple.count(":") != 2:
        raise Reject("KEY_MALFORMED", "generation identity must be birth:epoch:seq")
    if "hard_ceiling_s" not in exec_policy:
        raise Reject("KEY_MALFORMED", "exec policy must carry the hard ceiling (C5)")
    parts = {"g": gen_triple, "q": query, "c": retrieval_config, "p": exec_policy}
    c = canon(parts)
    return (c, hashlib.sha256(c.encode()).hexdigest())


class Run:
    """A producing execution offered for admission."""
    def __init__(self, completed, result=None, disclosures=None, lateness_s=None,
                 interrupted=False, lower_bound_s=None):
        self.completed = bool(completed)
        self.interrupted = bool(interrupted)
        self.result = result
        self.disclosures = disclosures or {}
        self.lateness_s = lateness_s
        self.lower_bound_s = lower_bound_s


class ExactGenCache:
    eviction_policy = "LRU-experimental"  # LRU-vs-clock open per Q1.5; recorded

    def __init__(self, max_entries, max_bytes, refuse_when_full=False):
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self.refuse_when_full = refuse_when_full
        self._d = collections.OrderedDict()  # digest -> entry
        self._bytes = 0
        self.evictions = []

    @staticmethod
    def _size(result, disclosures):
        return len(canon(result).encode()) + len(canon(disclosures).encode())

    def __len__(self):
        return len(self._d)

    def admit(self, key, run):
        """Admit a completed run under key=(canon,digest). Returns
        ('ADMITTED', evicted) | ('REFUSED(capacity)', reason). Partials raise."""
        c, dgst = key
        if not run.completed or run.interrupted:
            raise Reject("ADMIT_REFUSED_PARTIAL",
                         "hard-stopped/interrupted partial never admitted as complete; "
                         f"lower_bound_s={run.lower_bound_s}")
        # Lateness alone never disqualifies (C5): completed-late is eligible.
        size = self._size(run.result, run.disclosures)
        if self.refuse_when_full and (len(self._d) >= self.max_entries
                                      or self._bytes + size > self.max_bytes):
            return ("REFUSED(capacity)",
                    f"capacity: entries {len(self._d)}/{self.max_entries}, "
                    f"bytes {self._bytes + size}/{self.max_bytes}")
        evicted = []
        while (len(self._d) >= self.max_entries
               or self._bytes + size > self.max_bytes) and self._d:
            k, e = self._d.popitem(last=False)  # eviction always safe (Q1.5)
            self._bytes -= e["size"]
            evicted.append(k)
            self.evictions.append(k)
        if dgst in self._d:  # re-admit same key: replace
            self._bytes -= self._d[dgst]["size"]
            del self._d[dgst]
        self._d[dgst] = {"key_canon": c, "result": run.result,
                         "disclosures": run.disclosures,
                         "original_lateness_s": run.lateness_s,
                         "size": size, "admitted_at": time.time()}
        self._d.move_to_end(dgst)
        self._bytes += size
        return ("ADMITTED", evicted)

    def lookup(self, key):
        """Exact-key serve only. MISS unless the full key matches, so old-gen
        or old-config entries can never serve a new query. Returns None (miss)
        or a hit dict distinguishing original lateness from current latency."""
        t0 = time.perf_counter()
        c, dgst = key
        e = self._d.get(dgst)
        if e is None or e["key_canon"] != c:
            return None
        self._d.move_to_end(dgst)
        return {"result": e["result"], "disclosures": e["disclosures"],
                "original_lateness_s": e["original_lateness_s"],
                "current_latency_s": time.perf_counter() - t0,
                "key_digest": dgst}


class AssessmentLog:
    """Assessment records: S-02 term, S-02 ownership distinct from the
    S-04/query-path cache that records them."""

    def __init__(self, con):
        con.executescript(ASSESS_SCHEMA)
        self.con = con

    def record(self, assess_id, term, scope, verdict, detail):
        self.con.execute("INSERT INTO assessments(assess_id,term,owner,recorded_by,"
                         "scope,verdict,detail,ts) VALUES(?,?,?,?,?,?,?,?)",
                         (assess_id, term, "S-02", "S-04/query-path-cache",
                          scope, verdict, detail, time.time()))

    def get(self, assess_id):
        return self.con.execute("SELECT assess_id,term,owner,recorded_by,scope,"
                                "verdict,detail FROM assessments WHERE assess_id=?",
                                (assess_id,)).fetchone()
