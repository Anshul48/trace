"""Per-view retirement tombstones (I3: eligibility never coalesced).

Current views hold a flat set (O(1) lookup, mutated in place on advance).
Retained (straggler) views hold an immutable chain node: O(corrections in
that advance) snapshot cost, no O(R) copy on the advance path. Straggler
lookups walk the chain (rare); chains flatten past depth 16.
"""

from tlsys.serving.lexical import toks

FLATTEN_DEPTH = 16


class Tombstones:
    def __init__(self, parent=None, added=frozenset(), live=None,
                 since=None):
        self._parent = parent          # older immutable node or None
        self._added = frozenset(added)  # docs added at this node
        # Live (current-view) state; None on frozen retained nodes.
        self._live = None if live is None else set(live)
        self._since = set() if since is None else set(since)
        self._head = None  # latest snapshot node (live nodes only)

    @classmethod
    def live_empty(cls):
        return cls(live=set())

    def __contains__(self, doc):
        if self._live is not None:
            return doc in self._live
        node = self
        while node is not None:
            if doc in node._added:
                return True
            node = node._parent
        return False

    def add_live(self, docs):
        """In-place add for the CURRENT view only."""
        if self._live is None:
            raise ValueError("add_live on a frozen tombstone node")
        for d in docs:
            if d not in self._live:
                self._live.add(d)
                self._since.add(d)

    def snapshot(self):
        """O(new corrections) immutable node for a retained view."""
        if self._live is None:
            raise ValueError("snapshot on a frozen tombstone node")
        node = Tombstones(parent=self._head, added=frozenset(self._since))
        self._since = set()
        if node.chain_depth() > FLATTEN_DEPTH:
            node = Tombstones(parent=None, added=frozenset(self._live))
        self._head = node
        return node

    def materialize(self):
        if self._live is not None:
            return set(self._live)
        out = set()
        node = self
        while node is not None:
            out |= node._added
            node = node._parent
        return out

    def sorted_docs(self):
        return sorted(self.materialize())

    def chain_depth(self):
        d = 0
        node = self
        while node is not None:
            d += 1
            node = node._parent
        return d


def token_adjustments(retired_texts):
    """Exact BM25 stat adjustments for retiring atoms: tokenize each
    retired atom's text (O(retired doc)); returns (total_tokens, df_map)
    with integer counts for exact subtraction."""
    df = {}
    total = 0
    for text in retired_texts:
        ts = toks(text)
        total += len(ts)
        for t in set(ts):
            df[t] = df.get(t, 0) + 1
    return total, df
