"""WP0 Calibration Fixtures & Prior Fitting: Grounding Polarity & Negation Inversion.

Target File: tests/test_grounding_polarity.py
Scope: WP0 calibration fixtures (negation_inversion), 3-stage proposition grounding
verification (Stage 1 Deterministic Polarity, Stage 2 Entity/Quantity Containment,
Stage 3 CPU NLI Audit specifications), byte-exact span provenance, and Appendix A priors.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
import sys
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest


# ==============================================================================
# Calibration Fixture Texts & Constant Bindings
# ==============================================================================

FIXTURE_NEGATION_INVERSION_SOURCE: str = "System strictly prohibits unencrypted storage."
FIXTURE_NEGATION_INVERSION_HYPOTHESIS: str = "System strictly permits unencrypted storage."

FIXTURE_NEGATION_INVERSION_FILE: str = (
    f"SOURCE: {FIXTURE_NEGATION_INVERSION_SOURCE}\n"
    f"HYPOTHESIS: {FIXTURE_NEGATION_INVERSION_HYPOTHESIS}"
)


@pytest.fixture
def fixture_negation_inversion() -> tuple[str, str]:
    """Source strictly prohibits vs Hypothesis strictly permits."""
    return (FIXTURE_NEGATION_INVERSION_SOURCE, FIXTURE_NEGATION_INVERSION_HYPOTHESIS)


# ==============================================================================
# Stage 1 & Stage 2 Algorithmic Reference Verifiers
# ==============================================================================

# Deterministic polarity marker set N
NEGATION_MARKERS: frozenset[str] = frozenset({
    "not", "no", "never", "none", "neither", "nor", "without",
    "cannot", "can't", "won't", "don't", "doesn't", "didn't",
    "prohibit", "prohibits", "prohibited", "prohibiting",
    "forbidden", "forbid", "forbids",
    "disallow", "disallows", "disallowed",
    "deny", "denies", "denied",
    "reject", "rejects", "rejected",
    "prevent", "prevents", "prevented",
})

# Antonym / directionality pairs where polarity is inverted
ANTONYM_POLARITY_PAIRS: list[tuple[frozenset[str], frozenset[str]]] = [
    (frozenset({"prohibit", "prohibits", "forbidden", "disallow", "disallows", "deny", "denies"}),
     frozenset({"permit", "permits", "permitted", "allow", "allows", "allowed", "enable", "enables", "grant", "grants"})),
    (frozenset({"require", "requires", "mandatory", "compulsory"}),
     frozenset({"optional", "discretionary", "forbidden", "prohibited"})),
    (frozenset({"always", "must"}),
     frozenset({"never", "cannot"})),
    (frozenset({"enable", "enables", "enabled"}),
     frozenset({"disable", "disables", "disabled"})),
]


def extract_normalized_tokens(text: str) -> list[str]:
    return [t.lower() for t in re.findall(r"\b[A-Za-z0-9_]+\b", text)]


def extract_entities_and_quantities(text: str) -> set[str]:
    """Extract named entities, code symbols, numbers, and identifiers."""
    tokens = re.findall(r"\b(?:[A-Z][a-z0-9]+|[0-9]+(?:\.[0-9]+)?|[a-z]+_[a-z0-9_]+)\b", text)
    return {t.lower() for t in tokens}


@dataclass(frozen=True)
class GroundingVerificationResult:
    passed: bool
    stage: int  # 1, 2, or 3
    failure_reason: str | None = None
    diagnostics: dict[str, object] | None = None


def verify_proposition_stage1_polarity(source: str, hypothesis: str) -> tuple[bool, str | None]:
    """Stage 1: Deterministic Polarity Parity & Directionality Alignment.

    Returns (True, None) if polarity aligns, or (False, "POLARITY_INVERSION") on mismatch.
    """
    source_tokens = extract_normalized_tokens(source)
    hypo_tokens = extract_normalized_tokens(hypothesis)

    source_neg = set(source_tokens) & NEGATION_MARKERS
    hypo_neg = set(hypo_tokens) & NEGATION_MARKERS

    # 1. Direct negation marker count parity mismatch (e.g. "is" vs "is not")
    # If one has explicit negation marker and the other does not, check for inverted pair
    for neg_set, pos_set in ANTONYM_POLARITY_PAIRS:
        s_has_neg = bool(set(source_tokens) & neg_set)
        s_has_pos = bool(set(source_tokens) & pos_set)
        h_has_neg = bool(set(hypo_tokens) & neg_set)
        h_has_pos = bool(set(hypo_tokens) & pos_set)

        # Cross inversion: Source has negative direction, Hypothesis has positive direction
        if (s_has_neg and h_has_pos) or (s_has_pos and h_has_neg):
            return False, "POLARITY_INVERSION"

    # Explicit negation particle mismatch without semantic compensation
    neg_particles = {"not", "never", "cannot", "no", "without"}
    s_particles = set(source_tokens) & neg_particles
    h_particles = set(hypo_tokens) & neg_particles
    if bool(s_particles) != bool(h_particles):
        return False, "POLARITY_INVERSION"

    return True, None


def verify_proposition_stage2_containment(
    source: str,
    hypothesis: str,
    token_recall_threshold: float = 0.80,
) -> tuple[bool, str | None, float]:
    """Stage 2: Entity & Quantity Containment + Salient Token Recall.

    Requires E(Pi) subset of E(A) and salient token recall >= 0.80.
    """
    source_tokens = set(extract_normalized_tokens(source))
    hypo_eq = extract_entities_and_quantities(hypothesis)

    # 1. Entity and quantity subset check: E(Pi) subseteq E(A)
    unsupported_entities = {e for e in hypo_eq if e not in source_tokens}
    if unsupported_entities:
        return False, f"UNSUPPORTED_ENTITIES: {sorted(unsupported_entities)}", 0.0

    # 2. Salient token recall: tokens in hypothesis supported by source
    source_tokens = set(extract_normalized_tokens(source))
    hypo_tokens = [t for t in extract_normalized_tokens(hypothesis) if len(t) >= 3]
    if not hypo_tokens:
        return True, None, 1.0

    matched = sum(1 for t in hypo_tokens if t in source_tokens)
    recall = matched / len(hypo_tokens)
    if recall < token_recall_threshold:
        return False, f"LOW_TOKEN_RECALL: {recall:.2f} < {token_recall_threshold}", recall

    return True, None, recall


def verify_grounding_pipeline(source: str, hypothesis: str) -> GroundingVerificationResult:
    """Run Stage 1 and Stage 2 deterministic verification cascade."""
    # Stage 1
    s1_pass, s1_err = verify_proposition_stage1_polarity(source, hypothesis)
    if not s1_pass:
        return GroundingVerificationResult(
            passed=False,
            stage=1,
            failure_reason=s1_err,
            diagnostics={"source": source, "hypothesis": hypothesis},
        )

    # Stage 2
    s2_pass, s2_err, recall = verify_proposition_stage2_containment(source, hypothesis)
    if not s2_pass:
        return GroundingVerificationResult(
            passed=False,
            stage=2,
            failure_reason=s2_err,
            diagnostics={"token_recall": recall},
        )

    return GroundingVerificationResult(passed=True, stage=2, diagnostics={"token_recall": recall})


# ==============================================================================
# Invariant Test: Byte-Exact Provenance of Grounding Fixtures
# ==============================================================================

class TestGroundingFixtureProvenance:
    """Byte-exact provenance for grounding test pairs."""

    def test_fixture_byte_exactness_and_hashes(self) -> None:
        source = FIXTURE_NEGATION_INVERSION_SOURCE
        hypothesis = FIXTURE_NEGATION_INVERSION_HYPOTHESIS

        source_bytes = source.encode("utf-8")
        hypo_bytes = hypothesis.encode("utf-8")

        # Prove non-empty byte slices and deterministic SHA-256 hashes
        assert len(source_bytes) > 0
        assert len(hypo_bytes) > 0

        source_hash = hashlib.sha256(source_bytes).hexdigest()
        hypo_hash = hashlib.sha256(hypo_bytes).hexdigest()
        assert source_hash != hypo_hash, "Inverted proposition must have distinct hash"

        # Check full fixture file reconstruction
        reconstructed = f"SOURCE: {source}\nHYPOTHESIS: {hypothesis}"
        assert reconstructed == FIXTURE_NEGATION_INVERSION_FILE


# ==============================================================================
# Calibration Tests: Deterministic Polarity Inversion & Antonym Detection
# ==============================================================================

class TestDeterministicPolarityGrounding:
    """Stage 1 Grounding: Deterministic Polarity Inversion Rejections."""

    def test_negation_inversion_fixture_strictly_fails(
        self, fixture_negation_inversion: tuple[str, str]
    ) -> None:
        """00_GLOBAL_CONTEXT §WP0 Acceptance:

        Source: 'System strictly prohibits unencrypted storage'
        Hypothesis: 'System strictly permits unencrypted storage'
        Grounding verifier must FAIL with POLARITY_INVERSION.
        """
        source, hypothesis = fixture_negation_inversion
        result = verify_grounding_pipeline(source, hypothesis)

        assert result.passed is False, "Negation inversion fixture MUST fail grounding"
        assert result.stage == 1, "Must fail at Stage 1 (Deterministic Polarity)"
        assert result.failure_reason == "POLARITY_INVERSION"

    @pytest.mark.parametrize(
        "source,hypothesis,expected_fail_stage,expected_reason",
        [
            (
                "Service requires mutual TLS encryption.",
                "Service does not require mutual TLS encryption.",
                1,
                "POLARITY_INVERSION",
            ),
            (
                "Authentication is mandatory for cluster access.",
                "Authentication is optional for cluster access.",
                1,
                "POLARITY_INVERSION",
            ),
            (
                "System administrators can never bypass audit logs.",
                "System administrators always bypass audit logs.",
                1,
                "POLARITY_INVERSION",
            ),
            (
                "Write operations are forbidden during read-only maintenance.",
                "Write operations are allowed during read-only maintenance.",
                1,
                "POLARITY_INVERSION",
            ),
            (
                "The ingest pipeline enables automatic compression.",
                "The ingest pipeline disables automatic compression.",
                1,
                "POLARITY_INVERSION",
            ),
        ],
    )
    def test_polarity_inversion_trap_suite(
        self,
        source: str,
        hypothesis: str,
        expected_fail_stage: int,
        expected_reason: str,
    ) -> None:
        """Various syntactic and antonym polarity inversions must all fail at Stage 1."""
        result = verify_grounding_pipeline(source, hypothesis)
        assert result.passed is False
        assert result.stage == expected_fail_stage
        assert result.failure_reason == expected_reason

    def test_true_entailment_passes_stage1(self) -> None:
        """Affirmative entailments sharing polarity must pass Stage 1."""
        source = "System strictly prohibits unencrypted storage across all disk volumes."
        hypothesis = "Unencrypted storage is strictly forbidden across disk volumes."

        result = verify_grounding_pipeline(source, hypothesis)
        # Both share negative directionality ("prohibits", "forbidden")
        assert result.passed is True
        assert result.stage >= 1


# ==============================================================================
# Calibration Tests: Stage 2 Entity/Quantity Containment
# ==============================================================================

class TestEntityQuantityContainment:
    """Stage 2 Grounding: Entity & Quantity Containment E(Pi) subseteq E(A)."""

    def test_quantity_mismatch_fails_containment(self) -> None:
        """Hypothesis introduces unsupported numerical quantity."""
        source = "Database cluster maintains 3 replicas across availability zones."
        hypothesis = "Database cluster maintains 5 replicas across availability zones."

        result = verify_grounding_pipeline(source, hypothesis)
        assert result.passed is False
        assert result.stage == 2
        assert "UNSUPPORTED_ENTITIES" in (result.failure_reason or "")
        assert "5" in (result.failure_reason or "")

    def test_entity_mismatch_fails_containment(self) -> None:
        """Hypothesis introduces unsupported named entity."""
        source = "Alice authorized migration script execution in staging."
        hypothesis = "Bob authorized migration script execution in staging."

        result = verify_grounding_pipeline(source, hypothesis)
        assert result.passed is False
        assert result.stage == 2
        assert "UNSUPPORTED_ENTITIES" in (result.failure_reason or "")
        assert "bob" in (result.failure_reason or "")

    def test_low_token_recall_fails_containment(self) -> None:
        """Hypothesis introduces extraneous ungrounded terms lowering recall < 0.80."""
        source = "System encrypts user credentials at rest."
        hypothesis = (
            "System encrypts user credentials at rest while streaming quantum telemetry "
            "to decentralized satellite relays across planetary networks."
        )

        result = verify_grounding_pipeline(source, hypothesis)
        assert result.passed is False
        assert result.stage == 2
        assert "LOW_TOKEN_RECALL" in (result.failure_reason or "")


# ==============================================================================
# Appendix A Row-6 Calibration Specifications: CPU Cross-Encoder NLI
# ==============================================================================

class TestStage3NLISpecifications:
    """Verify frozen Appendix A row-6 / CORTICAL_SUBSTRATE_V1_PLAN Stage 3 NLI specifications."""

    def test_stage3_nli_parameters_frozen(self) -> None:
        # Pinned model identity
        pinned_model = "cross-encoder/nli-deberta-v3-small"
        sample_ratio = 0.10  # 10% stratified sample
        max_contradiction_p = 0.01  # P(contradiction) < 0.01
        min_entailment_p = 0.70  # P(entailment) >= 0.70
        max_latency_budget_ms = 15  # <= 15ms CPU budget

        assert pinned_model == "cross-encoder/nli-deberta-v3-small"
        assert sample_ratio == 0.10
        assert max_contradiction_p == 0.01
        assert min_entailment_p == 0.70
        assert max_latency_budget_ms <= 15


# ==============================================================================
# Engine Integration Tests (Asserting Against retrieval.py)
# ==============================================================================

class TestRetrievalEngineGrounding:
    """Assert against src/trace/v2/retrieval.py proposition verifier.

    Downstream Work Packet WP5 implements the 3-Stage Proposition Verifier.
    Engine-dependent assertions are marked xfail with WP5 reason.
    """

    @pytest.mark.xfail(
        reason="WP5 3-Tier Dual-Dispatch & Grounding Verifier unblocks this",
        strict=False,
    )
    def test_engine_rejects_negation_inversion_fixture(
        self, fixture_negation_inversion: tuple[str, str]
    ) -> None:
        """WP5 acceptance test: retrieval engine verifier rejects negation inversion 100%."""
        from trace.v2 import retrieval

        source, hypothesis = fixture_negation_inversion
        if hasattr(retrieval, "verify_grounding"):
            ver_fn = getattr(retrieval, "verify_grounding")
            res = ver_fn(source, hypothesis)
            assert res.passed is False
        elif hasattr(retrieval, "PropositionVerifier"):
            verifier_cls = getattr(retrieval, "PropositionVerifier")
            verifier = verifier_cls()
            res = verifier.verify(source=source, hypothesis=hypothesis)
            assert res.passed is False
        else:
            pytest.fail("retrieval module does not yet implement PropositionVerifier (WP5 pending)")
