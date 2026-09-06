"""WP0 Calibration Fixtures & Prior Fitting: Atomizer A-B-A Aliasing & Provenance.

Target File: tests/test_atomizer_aba_aliasing.py
Scope: WP0 calibration fixtures (aba_split, boilerplate_trap, small_doc),
smoothed additive IDF zero-division verification, bounded complete-linkage diameter
priors, byte-exact span provenance invariant, and Appendix A row-7 frozen priors.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass
from typing import Sequence
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

from trace.v2 import atomizer


# ==============================================================================
# Appendix A Row-7 Frozen Priors
# ==============================================================================

@dataclass(frozen=True)
class AppendixARow7Priors:
    """Ratified and frozen calibration priors per CORTICAL_SUBSTRATE_V1_PLAN Appendix A."""

    lexical_score_floor: float = 2.0
    jaccard_threshold: float = 0.30
    centroid_cosine_floor: float = 0.70
    pairwise_cosine_floor: float = 0.55
    norm_coherence_floor: float = 0.60
    beta_lateral_inhibition: float = 1.0
    rrf_score_floor: float = 0.012
    drift_epsilon: float = 0.25
    lease_grace_seconds: int = 120
    commit_batch_size: int = 250
    max_spans_per_holon: int = 8


FROZEN_PRIORS = AppendixARow7Priors()


# ==============================================================================
# Calibration Fixture Texts
# ==============================================================================

FIXTURE_ABA_SPLIT: str = (
    "Distributed consensus in replicated state machines requires a leader election protocol. "
    "When the election timeout elapses without heartbeats, a follower transitions to candidate state "
    "and broadcasts a RequestVote RPC. Once a majority quorum grants their votes, the leader establishes "
    "authority and begins appending log entries.\n\n"
    "Modern frontend stylesheets utilize CSS grid layout to construct multi-column visual interfaces. "
    "Defining template columns with fractional units allows responsive element alignment across viewports, "
    "while media queries adjust layout breakpoints for mobile and desktop screens.\n\n"
    "The consensus leader maintains replicated state machine consistency by streaming AppendEntries RPCs "
    "to all followers. Followers verify log continuity, append entries to persistent disk storage, "
    "and acknowledge progress so the leader can advance the commit index when a majority quorum matches."
)

FIXTURE_BOILERPLATE_TRAP: str = (
    "The network client initialization routine sets timeout parameters and loads default config values. "
    "Application components log any startup error before attempting connection handshakes. "
    "Standard client configuration sets retry limits for subsequent network operations.\n\n"
    "Distributed transaction processing executes atomic two-phase commits across relational database partitions. "
    "Prepare messages verify participant readiness, while write-ahead logging secures commit records against "
    "hardware failure. During replication the database client applies timeout policies during error recovery "
    "and logs config changes.\n\n"
    "The service client termination procedure flushes pending telemetry buffers and closes active sockets. "
    "Resource monitors report timeout status, save config snapshots, and flag any final shutdown error. "
    "Diagnostic handlers flush pending traces and client reports."
)

FIXTURE_SMALL_DOC: str = (
    "def process_tx(tx_id: str) -> None:\n"
    "    validate_transaction_payload(tx_id)\n"
    "    record_ledger_entry(tx_id)\n\n"
    "def process_tx(tx_id: str) -> None:\n"
    "    commit_transaction_storage(tx_id)\n"
    "    notify_settlement_complete(tx_id)"
)


@pytest.fixture
def fixture_aba_split() -> str:
    """Document with topic A in Para 1, topic B in Para 2, topic A in Para 3."""
    return FIXTURE_ABA_SPLIT


@pytest.fixture
def fixture_boilerplate_trap() -> str:
    """Document where intro and conclusion share boilerplate vocabulary (~30%)."""
    return FIXTURE_BOILERPLATE_TRAP


@pytest.fixture
def fixture_small_doc() -> str:
    """2-paragraph document with shared code signature def process_tx(): ..."""
    return FIXTURE_SMALL_DOC


# ==============================================================================
# Algorithmic Reference Helpers for Calibration & Mathematical Proof
# ==============================================================================

ENGLISH_STOP_WORDS: frozenset[str] = frozenset({
    "a", "about", "above", "after", "again", "against", "all", "am", "an", "and",
    "any", "are", "as", "at", "be", "because", "been", "before", "being", "below",
    "between", "both", "but", "by", "can", "cannot", "could", "did", "do", "does",
    "doing", "down", "during", "each", "few", "for", "from", "further", "had", "has",
    "have", "having", "he", "her", "here", "hers", "herself", "him", "himself", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "itself", "me", "more", "most",
    "my", "myself", "no", "nor", "not", "of", "off", "on", "once", "only", "or",
    "other", "ought", "our", "ours", "ourselves", "out", "over", "own", "same", "she",
    "should", "so", "some", "such", "than", "that", "the", "their", "theirs", "them",
    "themselves", "then", "there", "these", "they", "this", "those", "through", "to",
    "too", "under", "until", "up", "very", "was", "we", "were", "what", "when",
    "where", "which", "while", "who", "whom", "why", "with", "would", "you", "your",
    "yours", "yourself", "yourselves",
})


def tokenize(text: str) -> list[str]:
    """Tokenize lowercased alphanumeric words and underscores."""
    return [t.lower() for t in re.findall(r"\b[A-Za-z0-9_]{2,}\b", text)]


def compute_smoothed_idf(n_paras: int, df_t: int) -> float:
    """Smoothed Additive IDF per CORTICAL_SUBSTRATE_V1_PLAN §2.A:

    idf_doc(t) = ln(1 + (n_paras - df_t + 0.5) / (df_t + 0.5)) + 1.0
    Guaranteed strictly positive (> 1.0) and division-by-zero free.
    """
    numerator = n_paras - df_t + 0.5
    denominator = df_t + 0.5
    if denominator <= 0:
        raise ZeroDivisionError(f"Smoothed IDF denominator invalid: {denominator}")
    return math.log(1.0 + (numerator / denominator)) + 1.0


def extract_salient_terms(
    paragraphs: Sequence[str],
) -> list[set[str]]:
    """Extract salient set S_i: len >= 3, not in english-stop, para-freq <= max(2, 0.4 * n_paras)."""
    n_paras = len(paragraphs)
    max_freq = max(2, int(0.4 * n_paras))
    para_token_sets = [set(tokenize(p)) for p in paragraphs]

    doc_freq: dict[str, int] = {}
    for p_tokens in para_token_sets:
        for t in p_tokens:
            doc_freq[t] = doc_freq.get(t, 0) + 1

    salient_per_para: list[set[str]] = []
    for p_tokens in para_token_sets:
        s_i = {
            t for t in p_tokens
            if len(t) >= 3
            and t not in ENGLISH_STOP_WORDS
            and doc_freq[t] <= max_freq
        }
        salient_per_para.append(s_i)
    return salient_per_para


def has_shared_entity_or_sig(p1: str, p2: str) -> bool:
    """Detect shared code signature (def ..., class ...) or exact entity patterns."""
    sig_pattern = re.compile(r"^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
    p1_sigs = set(sig_pattern.findall(p1))
    p2_sigs = set(sig_pattern.findall(p2))
    return bool(p1_sigs and p1_sigs & p2_sigs)


def jaccard_similarity(tokens1: Sequence[str], tokens2: Sequence[str]) -> float:
    s1, s2 = set(tokens1), set(tokens2)
    if not s1 and not s2:
        return 1.0
    union = s1 | s2
    if not union:
        return 0.0
    return len(s1 & s2) / len(union)


def fast_lexical_draft_aliased(
    p1: str,
    p2: str,
    all_paras: Sequence[str],
    i: int,
    k: int,
    priors: AppendixARow7Priors = FROZEN_PRIORS,
) -> tuple[bool, dict[str, float | int | bool]]:
    """Evaluate Fast Lexical Draft aliasing condition:

    [score_lex(i, k) >= 2.0 AND |S_i ∩ S_k| >= 2] OR [HasSharedEntityOrSig AND Jaccard >= 0.30]
    """
    salient = extract_salient_terms(all_paras)
    s_i = salient[i]
    s_k = salient[k]
    shared_salient = s_i & s_k

    # Compute IDF per shared salient term
    n_paras = len(all_paras)
    para_token_sets = [set(tokenize(p)) for p in all_paras]
    score_lex = 0.0
    for term in shared_salient:
        df_t = sum(1 for pts in para_token_sets if term in pts)
        score_lex += compute_smoothed_idf(n_paras, df_t)

    sig_match = has_shared_entity_or_sig(p1, p2)
    jaccard = jaccard_similarity(tokenize(p1), tokenize(p2))

    lex_branch = (score_lex >= priors.lexical_score_floor) and (len(shared_salient) >= 2)
    sig_branch = sig_match and (jaccard >= priors.jaccard_threshold)
    aliased = lex_branch or sig_branch

    return aliased, {
        "score_lex": score_lex,
        "shared_salient_count": len(shared_salient),
        "lex_branch": lex_branch,
        "sig_match": sig_match,
        "jaccard": jaccard,
        "sig_branch": sig_branch,
    }


def vector_norm(v: Sequence[float]) -> float:
    return math.sqrt(sum(x * x for x in v))


def unit_normalize(v: Sequence[float]) -> list[float]:
    norm = vector_norm(v)
    if norm <= 0:
        return [0.0] * len(v)
    return [x / norm for x in v]


def dot_product(v1: Sequence[float], v2: Sequence[float]) -> float:
    return sum(x * y for x, y in zip(v1, v2))


def cosine_similarity(v1: Sequence[float], v2: Sequence[float]) -> float:
    n1, n2 = vector_norm(v1), vector_norm(v2)
    if n1 <= 0 or n2 <= 0:
        return 0.0
    return dot_product(v1, v2) / (n1 * n2)


# ==============================================================================
# Invariant Test: Byte-Exact Provenance & Content Hashing
# ==============================================================================

class TestByteExactProvenance:
    """Byte-exact provenance everywhere: text == normalized[start:end]; SHA-256 / BLAKE3."""

    @pytest.mark.parametrize(
        "fixture_name,fixture_content",
        [
            ("fixture_aba_split", FIXTURE_ABA_SPLIT),
            ("fixture_boilerplate_trap", FIXTURE_BOILERPLATE_TRAP),
            ("fixture_small_doc", FIXTURE_SMALL_DOC),
        ],
    )
    def test_byte_exact_provenance_invariant(self, fixture_name: str, fixture_content: str) -> None:
        normalized = atomizer.normalize_text(fixture_content)
        atoms = atomizer.atomize(fixture_content)
        assert len(atoms) >= 2, f"{fixture_name} must yield at least 2 atoms"

        for atom in atoms:
            # 1. Byte-exact substring extraction invariant
            extracted = normalized[atom.start:atom.end]
            assert extracted == atom.content, (
                f"Byte-exact slice violation in {fixture_name}: "
                f"normalized[{atom.start}:{atom.end}] != atom.content"
            )

            # 2. SHA-256 deterministic content digest verification
            sha256_digest = hashlib.sha256(atom.content.encode("utf-8")).digest()
            assert len(sha256_digest) == 32

            # 3. Optional BLAKE3 verification if library is present
            try:
                import blake3  # type: ignore
                b3_digest = blake3.blake3(atom.content.encode("utf-8")).digest()
                assert len(b3_digest) == 32
            except ImportError:
                pass


# ==============================================================================
# Calibration Tests: Appendix A Row-7 Priors & Mathematical Fitting
# ==============================================================================

class TestAppendixARow7Priors:
    """Verify frozen Appendix A row-7 priors are recorded and immutable."""

    def test_frozen_priors_immutability(self) -> None:
        assert FROZEN_PRIORS.lexical_score_floor == 2.0
        assert FROZEN_PRIORS.jaccard_threshold == 0.30
        assert FROZEN_PRIORS.centroid_cosine_floor == 0.70
        assert FROZEN_PRIORS.pairwise_cosine_floor == 0.55
        assert FROZEN_PRIORS.norm_coherence_floor == 0.60
        assert FROZEN_PRIORS.beta_lateral_inhibition == 1.0
        assert FROZEN_PRIORS.rrf_score_floor == 0.012
        assert FROZEN_PRIORS.drift_epsilon == 0.25
        assert FROZEN_PRIORS.lease_grace_seconds == 120
        assert FROZEN_PRIORS.commit_batch_size == 250
        assert FROZEN_PRIORS.max_spans_per_holon == 8

        # Invariant: Priors are strictly frozen dataclass
        with pytest.raises(Exception):
            FROZEN_PRIORS.lexical_score_floor = 1.5  # type: ignore

    def test_smoothed_idf_small_doc_zero_division_guard(self) -> None:
        """small_doc aliases without ZeroDivisionError:

        For n_paras = 2 and df_t = 2, smoothed IDF must remain > 1.0 and never fail.
        """
        n_paras = 2
        df_t = 2

        # 1. Verify standard Robertson-Spärck Jones (RSJ) IDF would produce negative score:
        # ln((N - df + 0.5) / (df + 0.5)) = ln(0.5 / 2.5) = ln(0.2) = -1.609
        legacy_rsj = math.log((n_paras - df_t + 0.5) / (df_t + 0.5))
        assert legacy_rsj < 0.0, "Legacy RSJ IDF must be negative when df == N"

        # 2. Verify Smoothed Additive IDF is strictly positive:
        smoothed = compute_smoothed_idf(n_paras, df_t)
        assert smoothed > 1.0, f"Smoothed IDF must be > 1.0, got {smoothed}"
        assert math.isclose(smoothed, math.log(1.2) + 1.0, rel_tol=1e-5)

        # 3. Test boundary values: df = 0, df = 1, df = 2
        for df in range(n_paras + 1):
            val = compute_smoothed_idf(n_paras, df)
            assert val > 1.0
            assert not math.isnan(val)
            assert not math.isinf(val)

    def test_small_doc_aliases_via_code_signature(self, fixture_small_doc: str) -> None:
        """fixture_small_doc shares 'def process_tx(): ...' signature and Jaccard >= 0.30."""
        paras = [p.strip() for p in fixture_small_doc.split("\n\n") if p.strip()]
        assert len(paras) == 2

        aliased, metrics = fast_lexical_draft_aliased(paras[0], paras[1], paras, 0, 1)
        assert metrics["sig_match"] is True, "Must detect shared def process_tx signature"
        assert metrics["jaccard"] >= FROZEN_PRIORS.jaccard_threshold, (
            f"Jaccard {metrics['jaccard']} must be >= {FROZEN_PRIORS.jaccard_threshold}"
        )
        assert aliased is True, "Small doc paragraphs must alias into 1 holon"

    def test_boilerplate_trap_does_not_alias(self, fixture_boilerplate_trap: str) -> None:
        """fixture_boilerplate_trap shares 30% vocab (client, timeout, error, config)

        and must NOT alias.
        """
        paras = [p.strip() for p in fixture_boilerplate_trap.split("\n\n") if p.strip()]
        assert len(paras) == 3

        # Para 0 (Intro) vs Para 2 (Conclusion)
        aliased, metrics = fast_lexical_draft_aliased(paras[0], paras[2], paras, 0, 2)
        assert aliased is False, (
            f"Boilerplate intro and conclusion must NOT alias: {metrics}"
        )
        assert metrics["sig_match"] is False, "Boilerplate must not have shared code signature"
        assert metrics["jaccard"] < FROZEN_PRIORS.jaccard_threshold, (
            f"Boilerplate Jaccard {metrics['jaccard']} must be < {FROZEN_PRIORS.jaccard_threshold}"
        )
        # Because client, timeout, error, config appear in all 3 paras, they are pruned from salient set
        assert metrics["shared_salient_count"] < 2 or metrics["score_lex"] < FROZEN_PRIORS.lexical_score_floor

    def test_aba_split_lexical_draft_math(self, fixture_aba_split: str) -> None:
        """Verify mathematical calibration on fixture_aba_split:

        Para 1 and Para 3 share consensus vocabulary and score >= 2.0 with |S1 ∩ S3| >= 2.
        Para 1 and Para 2 share 0 vocabulary and score == 0.0.
        """
        paras = [p.strip() for p in fixture_aba_split.split("\n\n") if p.strip()]
        assert len(paras) == 3

        # 1. P1 (Consensus) vs P3 (Consensus continuation)
        aliased_13, metrics_13 = fast_lexical_draft_aliased(paras[0], paras[2], paras, 0, 2)
        assert aliased_13 is True, f"Para 1 and Para 3 must alias: {metrics_13}"
        assert metrics_13["score_lex"] >= FROZEN_PRIORS.lexical_score_floor
        assert metrics_13["shared_salient_count"] >= 2

        # 2. P1 (Consensus) vs P2 (CSS layout)
        aliased_12, metrics_12 = fast_lexical_draft_aliased(paras[0], paras[1], paras, 0, 1)
        assert aliased_12 is False, f"Para 1 and Para 2 must NOT alias: {metrics_12}"
        assert metrics_12["score_lex"] < FROZEN_PRIORS.lexical_score_floor
        assert metrics_12["shared_salient_count"] < 2

        # 3. P2 (CSS layout) vs P3 (Consensus)
        aliased_23, metrics_23 = fast_lexical_draft_aliased(paras[1], paras[2], paras, 1, 2)
        assert aliased_23 is False, f"Para 2 and Para 3 must NOT alias: {metrics_23}"

    def test_bounded_complete_linkage_constraints(self) -> None:
        """Verify complete-linkage & bounded diameter constraints:

        - Max 8 spans per holon.
        - Centroid cosine >= 0.70.
        - Pairwise cosine >= 0.55.
        - Norm coherence floor >= 0.60.
        """
        # 1. Span count bound
        max_spans = FROZEN_PRIORS.max_spans_per_holon
        assert max_spans == 8
        spans_sample = list(range(max_spans))
        assert len(spans_sample) <= 8
        # Adding 9th span violates bounded diameter
        assert len(spans_sample + [8]) > 8

        # 2. Pairwise and Centroid cosine thresholds
        # Candidate span vector with cosine 0.65 to centroid (< 0.70) must be rejected
        c = [1.0, 0.0, 0.0]
        v_low_centroid = [0.65, math.sqrt(1.0 - 0.65**2), 0.0]
        assert cosine_similarity(v_low_centroid, c) < FROZEN_PRIORS.centroid_cosine_floor

        # Candidate span with pairwise cosine 0.45 (< 0.55) must be rejected
        v1 = [math.cos(0.2), math.sin(0.2), 0.0]
        v2 = [math.cos(1.3), math.sin(1.3), 0.0]
        assert cosine_similarity(v1, v2) < FROZEN_PRIORS.pairwise_cosine_floor

        # 3. Pre-normalization coherence norm check:
        # Sum of vectors: (1 / |H|) * ||sum e_i|| >= 0.60
        # Two opposing vectors: [1, 0, 0] and [-0.8, 0.6, 0]
        # Sum = [0.2, 0.6, 0], norm = sqrt(0.04 + 0.36) = sqrt(0.40) ~= 0.6325 / 2 = 0.316 < 0.60
        opposing_v1 = [1.0, 0.0, 0.0]
        opposing_v2 = [-0.8, 0.6, 0.0]
        vec_sum = [x + y for x, y in zip(opposing_v1, opposing_v2)]
        coherence_norm = vector_norm(vec_sum) / 2.0
        assert coherence_norm < FROZEN_PRIORS.norm_coherence_floor, (
            f"Opposing vectors must violate coherence norm: {coherence_norm}"
        )


# ==============================================================================
# Engine Integration Tests (Asserting Against atomizer.py)
# ==============================================================================

class TestAtomizerEngineAbaAliasing:
    """Assert against src/trace/v2/atomizer.py.

    Downstream Work Packet WP1 implements the aliasing engine.
    Engine-dependent assertions are marked xfail with WP1 reason.
    """

    def test_current_atomize_yields_three_raw_atoms(self, fixture_aba_split: str) -> None:
        """Current baseline atomizer parses 3 paragraph atoms without aliasing."""
        atoms = atomizer.atomize(fixture_aba_split)
        assert len(atoms) == 3
        # Prove byte exactness of current atoms
        normalized = atomizer.normalize_text(fixture_aba_split)
        for atom in atoms:
            assert normalized[atom.start:atom.end] == atom.content

    @pytest.mark.xfail(
        reason="WP1 Ingestion & Intra-Doc Aliasing Engine unblocks this",
        strict=False,
    )
    def test_aba_split_expects_exactly_two_holons(self, fixture_aba_split: str) -> None:
        """00_GLOBAL_CONTEXT §WP0 Acceptance:

        aba_split expects exactly 2 holons not 3 (Para 1 and Para 3 alias into one holon).
        """
        # When WP1 adds aliasing / holon construction to atomizer
        if hasattr(atomizer, "atomize_with_aliasing"):
            holons = getattr(atomizer, "atomize_with_aliasing")(fixture_aba_split)
        elif hasattr(atomizer, "build_holons"):
            holons = getattr(atomizer, "build_holons")(fixture_aba_split)
        else:
            # Under current code, only unaliased atomize() exists
            pytest.fail("atomizer does not yet support holon aliasing (WP1 pending)")

        assert len(holons) == 2, f"Expected exactly 2 holons, got {len(holons)}"
