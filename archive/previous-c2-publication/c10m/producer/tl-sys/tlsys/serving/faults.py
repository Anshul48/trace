"""Deterministic fault-injection hooks (spec section 4; FI rows 4,5,6,10,22).

Off by default. Tests arm hooks explicitly (no randomness, no env
dependence except the documented opt-in env names, which tests set
explicitly too). Product code calls faults.fire(name) at each kill point;
a tripped hook raises FaultTripped so the crash path is exercised exactly.
"""


class FaultTripped(Exception):
    def __init__(self, name, ctx=None):
        super().__init__(f"fault hook tripped: {name}")
        self.hook = name
        self.ctx = dict(ctx or {})


# Kill points (row 4): before/after each segment file write + rename +
# manifest publish. Corruption (row 5): corrupt_<file>/truncate_<file>.
# Row 6: config_skew. Row 10: compaction_kill (+ compaction_tails metering
# is done by the test). Row 22: enospc_segment, long_reader.
HOOKS = (
    "pre_vectors", "post_vectors",
    "pre_csr", "post_csr",
    "pre_text", "post_text",
    "pre_header", "post_header",
    "pre_rename", "post_rename",
    "pre_manifest", "post_manifest",
    "corrupt_vectors", "corrupt_csr", "corrupt_text", "corrupt_header",
    "truncate_vectors", "truncate_csr", "truncate_text", "truncate_header",
    "config_skew",
    "compaction_kill",
    "enospc_segment",
    "long_reader",
)

_armed = {}


def arm(name, mode="raise"):
    """Arm `name` (mode 'raise'; unknown names fail loud)."""
    if name not in HOOKS:
        raise ValueError(f"unknown fault hook: {name}")
    _armed[name] = mode


def disarm(name=None):
    if name is None:
        _armed.clear()
    else:
        _armed.pop(name, None)


def armed():
    return sorted(_armed)


def fire(name, **ctx):
    """At a kill point: raise FaultTripped iff armed. Returns False when
    disarmed (so `if fire(...):` also works for non-raise modes later)."""
    if _armed.get(name) is not None:
        raise FaultTripped(name, ctx)
    return False


def tripped(name):
    return name in _armed
