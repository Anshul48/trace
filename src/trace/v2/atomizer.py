"""Deterministic, text-first atomization with source-offset preservation.

Cortical Substrate V1.1 Ingestion & Intra-Doc Aliasing Engine.
Governing standard: docs/program/CORTICAL_SUBSTRATE_V1_PLAN.md §1, §2.A & Appendix A.
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field
from typing import Any, Sequence


# ==============================================================================
# Appendix A Row-7 Frozen Priors & Calibration Thresholds
# ==============================================================================

LEXICAL_SCORE_FLOOR: float = 2.0
JACCARD_THRESHOLD: float = 0.30
CENTROID_COSINE_FLOOR: float = 0.70
PAIRWISE_COSINE_FLOOR: float = 0.55
NORM_COHERENCE_FLOOR: float = 0.60
BETA_LATERAL_INHIBITION: float = 1.0
RRF_SCORE_FLOOR: float = 0.012
DRIFT_EPSILON: float = 0.25
LEASE_GRACE_SECONDS: int = 120
COMMIT_BATCH_SIZE: int = 250
MAX_SPANS_PER_HOLON: int = 8


# ==============================================================================
# Lexical Tokenization & Stop Words
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

_SIG_PATTERN = re.compile(r"^\s*(?:def|class)\s+([A-Za-z_][A-Za-z0-9_]*)", re.MULTILINE)
_PARAGRAPH = re.compile(r"\S(?:.*?\S)?(?=\n\s*\n|\Z)", re.DOTALL)
_BULLET = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9])")


# ==============================================================================
# Data Structures
# ==============================================================================

@dataclass(frozen=True)
class AtomDraft:
    """Canonical L0 episodic atom draft."""

    content: str
    start: int
    end: int
    ordinal: int
    parser_location: str
    content_hash: str = ""


@dataclass(frozen=True)
class HolonDraft:
    """Operational L1 Holon unit per CORTICAL_SUBSTRATE_V1_PLAN §1 & §2.A."""

    holon_id: str
    spans: list[tuple[int, int]]  # [(start, end), ...] byte offsets into normalized source
    atoms: list[AtomDraft]
    lex_sig: list[str]  # Top-32 string tokens (JSON array of strings)
    content: str
    file_id: str = ""
    doc_id: str = ""
    centroid_int8: bytes | None = None
    energy: float = 0.0
    tier: str = "nav"
    status: str = "ACTIVE"
    version: int = 1
    see_also: list[str] = field(default_factory=list)


# ==============================================================================
# Ingestion & Normalization Helpers
# ==============================================================================

def normalize_text(text: str) -> str:
    """Normalize line endings only; the resulting text is the stored evidence text."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end


def _split_bullets(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Return non-bullet runs and each bullet independently, preserving offsets."""
    spans: list[tuple[int, int]] = []
    lines = list(re.finditer(r"[^\n]+(?:\n|\Z)", text[start:end]))
    nonbullet_start: int | None = None
    nonbullet_end: int | None = None
    for line in lines:
        line_start = start + line.start()
        line_end = start + line.end()
        stripped = text[line_start:line_end].strip()
        if not stripped:
            continue
        if _BULLET.match(stripped):
            if nonbullet_start is not None and nonbullet_end is not None:
                spans.append(_trimmed_span(text, nonbullet_start, nonbullet_end))
                nonbullet_start = nonbullet_end = None
            spans.append(_trimmed_span(text, line_start, line_end))
        else:
            if nonbullet_start is None:
                nonbullet_start = line_start
            nonbullet_end = line_end
    if nonbullet_start is not None and nonbullet_end is not None:
        spans.append(_trimmed_span(text, nonbullet_start, nonbullet_end))
    return [(left, right) for left, right in spans if left < right]


def _split_long(text: str, start: int, end: int, max_chars: int) -> list[tuple[int, int]]:
    if end - start <= max_chars:
        return [(start, end)]
    segment = text[start:end]
    boundaries = [match.end() for match in _SENTENCE_END.finditer(segment)]
    spans: list[tuple[int, int]] = []
    cursor = 0
    while len(segment) - cursor > max_chars:
        limit = cursor + max_chars
        eligible = [point for point in boundaries if cursor < point <= limit]
        cut = eligible[-1] if eligible else limit
        left, right = _trimmed_span(text, start + cursor, start + cut)
        if left < right:
            spans.append((left, right))
        cursor = cut
        while cursor < len(segment) and segment[cursor].isspace():
            cursor += 1
    left, right = _trimmed_span(text, start + cursor, end)
    if left < right:
        spans.append((left, right))
    return spans


def atomize(text: str, *, max_chars: int = 1_200) -> list[AtomDraft]:
    """Atomize paragraphs first, bullets independently, then exceptionally long text.

    ``start`` and ``end`` point into the normalized source text held in the
    attachment, so an original context can be reconstructed without a document
    table becoming authoritative.
    """
    if max_chars < 100:
        raise ValueError("max_chars must be at least 100")
    normalized = normalize_text(text)
    spans: list[tuple[int, int]] = []
    for paragraph in _PARAGRAPH.finditer(normalized):
        start, end = _trimmed_span(normalized, paragraph.start(), paragraph.end())
        if start >= end:
            continue
        for item_start, item_end in _split_bullets(normalized, start, end):
            spans.extend(_split_long(normalized, item_start, item_end, max_chars))

    result: list[AtomDraft] = []
    for ordinal, (start, end) in enumerate(spans):
        content = normalized[start:end]
        c_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        result.append(
            AtomDraft(
                content=content,
                start=start,
                end=end,
                ordinal=ordinal,
                parser_location=f"char:{start}-{end}",
                content_hash=c_hash,
            )
        )
    return result


# ==============================================================================
# Mathematical & Lexical Priors Implementation
# ==============================================================================

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
    p1_sigs = set(_SIG_PATTERN.findall(p1))
    p2_sigs = set(_SIG_PATTERN.findall(p2))
    return bool(p1_sigs and p1_sigs & p2_sigs)


def jaccard_similarity(tokens1: Sequence[str], tokens2: Sequence[str]) -> float:
    """Token-level Jaccard similarity."""
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
    *,
    lexical_score_floor: float = LEXICAL_SCORE_FLOOR,
    jaccard_threshold: float = JACCARD_THRESHOLD,
) -> tuple[bool, dict[str, Any]]:
    """Evaluate Fast Lexical Draft aliasing condition:

    [score_lex(i, k) >= 2.0 AND |S_i ∩ S_k| >= 2] OR [HasSharedEntityOrSig AND Jaccard >= 0.30]
    """
    salient = extract_salient_terms(all_paras)
    s_i = salient[i]
    s_k = salient[k]
    shared_salient = s_i & s_k

    n_paras = len(all_paras)
    para_token_sets = [set(tokenize(p)) for p in all_paras]
    score_lex = 0.0
    for term in shared_salient:
        df_t = sum(1 for pts in para_token_sets if term in pts)
        score_lex += compute_smoothed_idf(n_paras, df_t)

    sig_match = has_shared_entity_or_sig(p1, p2)
    jaccard = jaccard_similarity(tokenize(p1), tokenize(p2))

    lex_branch = (score_lex >= lexical_score_floor) and (len(shared_salient) >= 2)
    sig_branch = sig_match and (jaccard >= jaccard_threshold)
    aliased = lex_branch or sig_branch

    return aliased, {
        "score_lex": score_lex,
        "shared_salient_count": len(shared_salient),
        "lex_branch": lex_branch,
        "sig_match": sig_match,
        "jaccard": jaccard,
        "sig_branch": sig_branch,
    }


# ==============================================================================
# Vector Math & Embedding Diameter Guards (WP1b / S^383 Hyperspherical)
# ==============================================================================

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


def compute_frechet_unit_centroid(vectors: Sequence[Sequence[float]]) -> list[float]:
    """Spherical Fréchet mean c_unit = c_bar / ||c_bar||_2 on S^{d-1}."""
    if not vectors:
        return []
    dim = len(vectors[0])
    sum_vec = [0.0] * dim
    for v in vectors:
        for idx, val in enumerate(v):
            sum_vec[idx] += val
    return unit_normalize(sum_vec)


def quantize_centroid_int8(unit_vector: Sequence[float]) -> bytes:
    """Symmetric int8 quantization: q = clip(round(c_unit * 127), -127, 127)."""
    quantized = [
        max(-127, min(127, int(round(val * 127.0))))
        for val in unit_vector
    ]
    return bytes(bytearray([x & 0xFF for x in quantized]))


def check_embedding_diameter_constraints(
    candidate_vec: Sequence[float],
    member_vecs: Sequence[Sequence[float]],
    *,
    centroid_floor: float = CENTROID_COSINE_FLOOR,
    pairwise_floor: float = PAIRWISE_COSINE_FLOOR,
    norm_coherence_floor: float = NORM_COHERENCE_FLOOR,
) -> tuple[bool, dict[str, float]]:
    """Enforce complete-linkage & bounded diameter constraints:

    - Centroid distance cap: cos(e(P_k), c_H) >= 0.70
    - Pairwise diameter bound: min_{P_j in spans(H)} cos(e(P_k), e(P_j)) >= 0.55
    - Norm coherence floor: (1 / (|H| + 1)) * ||sum_{P in H U {P_k}} e(P)||_2 >= 0.60
    """
    if not member_vecs:
        return True, {"centroid_cos": 1.0, "min_pairwise_cos": 1.0, "coherence_norm": 1.0}

    # 1. Pairwise diameter bound
    min_pw = min(cosine_similarity(candidate_vec, mv) for mv in member_vecs)
    if min_pw < pairwise_floor:
        return False, {"centroid_cos": 0.0, "min_pairwise_cos": min_pw, "coherence_norm": 0.0}

    # 2. Centroid distance cap
    centroid = compute_frechet_unit_centroid(member_vecs)
    cent_cos = cosine_similarity(candidate_vec, centroid)
    if cent_cos < centroid_floor:
        return False, {"centroid_cos": cent_cos, "min_pairwise_cos": min_pw, "coherence_norm": 0.0}

    # 3. Norm coherence floor of union
    all_vecs = list(member_vecs) + [candidate_vec]
    dim = len(candidate_vec)
    sum_vec = [0.0] * dim
    for v in all_vecs:
        for idx, val in enumerate(v):
            sum_vec[idx] += val
    coherence = vector_norm(sum_vec) / float(len(all_vecs))
    if coherence < norm_coherence_floor:
        return False, {"centroid_cos": cent_cos, "min_pairwise_cos": min_pw, "coherence_norm": coherence}

    return True, {"centroid_cos": cent_cos, "min_pairwise_cos": min_pw, "coherence_norm": coherence}


def extract_lex_sig(
    texts: Sequence[str],
    n_paras: int,
    doc_freq: dict[str, int],
    max_tokens: int = 32,
) -> list[str]:
    """Compute top-32 string tokens for a holon (Appendix A item 10)."""
    scored_tokens: dict[str, float] = {}
    for text in texts:
        for t in tokenize(text):
            if len(t) < 3 or t in ENGLISH_STOP_WORDS:
                continue
            df_t = doc_freq.get(t, 1)
            idf = compute_smoothed_idf(n_paras, df_t)
            scored_tokens[t] = scored_tokens.get(t, 0.0) + idf

    sorted_tokens = sorted(scored_tokens.keys(), key=lambda t: (-scored_tokens[t], t))
    return sorted_tokens[:max_tokens]


# ==============================================================================
# Holon Construction & Ingestion Engine (Two-Pass Intra-Doc Aliasing)
# ==============================================================================

def atomize_with_aliasing(
    text_or_atoms: str | Sequence[AtomDraft],
    *,
    doc_id: str = "",
    file_id: str = "",
    max_chars: int = 1_200,
    embeddings: Sequence[Sequence[float]] | None = None,
) -> list[HolonDraft]:
    """Two-pass intra-doc aliasing engine: fast lexical draft + complete-linkage diameter cap.

    Enforces:
    - Max 8 spans per holon (|spans| <= 8).
    - Disjunctive aliasing: P_lex OR P_entity.
    - Strict complete linkage (transitive closure strictly prohibited).
    - Optional WP1b hyperspherical diameter bounds when embeddings supplied.
    - Byte-exact multi-span provenance.
    """
    if isinstance(text_or_atoms, str):
        normalized = normalize_text(text_or_atoms)
        atoms = atomize(text_or_atoms, max_chars=max_chars)
    else:
        atoms = list(text_or_atoms)
        normalized = ""

    if not atoms:
        return []

    n_atoms = len(atoms)
    paragraphs = [a.content for a in atoms]
    salient_per_para = extract_salient_terms(paragraphs)
    para_token_sets = [set(tokenize(p)) for p in paragraphs]

    doc_freq: dict[str, int] = {}
    for p_tokens in para_token_sets:
        for t in p_tokens:
            doc_freq[t] = doc_freq.get(t, 0) + 1

    # Precompute pairwise lexical aliasing matrix
    aliased_matrix: dict[tuple[int, int], tuple[bool, float]] = {}
    for i in range(n_atoms):
        for k in range(i, n_atoms):
            if i == k:
                aliased_matrix[(i, k)] = (True, float("inf"))
                continue
            shared_salient = salient_per_para[i] & salient_per_para[k]
            score_lex = sum(
                compute_smoothed_idf(n_atoms, doc_freq.get(t, 1))
                for t in shared_salient
            )
            sig_match = has_shared_entity_or_sig(paragraphs[i], paragraphs[k])
            jaccard = jaccard_similarity(tokenize(paragraphs[i]), tokenize(paragraphs[k]))

            lex_ok = (score_lex >= LEXICAL_SCORE_FLOOR) and (len(shared_salient) >= 2)
            sig_ok = sig_match and (jaccard >= JACCARD_THRESHOLD)
            is_aliased = lex_ok or sig_ok
            affinity = score_lex if lex_ok else (jaccard if sig_ok else 0.0)
            aliased_matrix[(i, k)] = (is_aliased, affinity)
            aliased_matrix[(k, i)] = (is_aliased, affinity)

    # Complete-linkage clustering
    clusters: list[list[int]] = []
    see_also_links: dict[int, set[int]] = {}

    for k in range(n_atoms):
        best_c_idx: int | None = None
        best_affinity = -1.0

        for c_idx, cluster_members in enumerate(clusters):
            # 1. Capacity bound: maximum 8 spans per holon
            if len(cluster_members) >= MAX_SPANS_PER_HOLON:
                continue

            # 2. Complete-linkage constraint: k must alias with ALL members in cluster
            all_aliased = True
            total_affinity = 0.0
            for j in cluster_members:
                ok, aff = aliased_matrix[(j, k)]
                if not ok:
                    all_aliased = False
                    break
                total_affinity += aff

            if not all_aliased:
                for j in cluster_members:
                    if aliased_matrix[(j, k)][0]:
                        see_also_links.setdefault(k, set()).add(c_idx)
                continue

            # 3. Embedding constraints (WP1b async refinement)
            if embeddings is not None and len(embeddings) == n_atoms:
                member_vecs = [embeddings[j] for j in cluster_members]
                emb_ok, _metrics = check_embedding_diameter_constraints(
                    embeddings[k], member_vecs
                )
                if not emb_ok:
                    see_also_links.setdefault(k, set()).add(c_idx)
                    continue

            avg_affinity = total_affinity / len(cluster_members)
            if avg_affinity > best_affinity:
                best_affinity = avg_affinity
                best_c_idx = c_idx

        if best_c_idx is not None:
            clusters[best_c_idx].append(k)
        else:
            clusters.append([k])

    # Build HolonDraft instances
    holons: list[HolonDraft] = []
    for c_idx, member_indices in enumerate(clusters):
        member_atoms = [atoms[idx] for idx in member_indices]
        spans = [(a.start, a.end) for a in member_atoms]
        member_texts = [a.content for a in member_atoms]
        lex_sig = extract_lex_sig(member_texts, n_atoms, doc_freq)

        c_int8: bytes | None = None
        if embeddings is not None and len(embeddings) == n_atoms:
            m_vecs = [embeddings[idx] for idx in member_indices]
            frechet_c = compute_frechet_unit_centroid(m_vecs)
            c_int8 = quantize_centroid_int8(frechet_c)

        links: set[str] = set()
        for idx in member_indices:
            if idx in see_also_links:
                for target_c_idx in see_also_links[idx]:
                    if target_c_idx != c_idx:
                        links.add(f"holon_{target_c_idx + 1:04d}")

        h_id = f"holon_{c_idx + 1:04d}"
        combined_content = "\n\n".join(member_texts)

        holons.append(
            HolonDraft(
                holon_id=h_id,
                spans=spans,
                atoms=member_atoms,
                lex_sig=lex_sig,
                content=combined_content,
                file_id=file_id,
                doc_id=doc_id,
                centroid_int8=c_int8,
                energy=0.0,
                tier="nav",
                status="ACTIVE",
                version=1,
                see_also=sorted(links),
            )
        )

    return holons


def build_holons(
    text_or_atoms: str | Sequence[AtomDraft],
    *,
    doc_id: str = "",
    file_id: str = "",
    max_chars: int = 1_200,
    embeddings: Sequence[Sequence[float]] | None = None,
) -> list[HolonDraft]:
    """Alias to atomize_with_aliasing."""
    return atomize_with_aliasing(
        text_or_atoms,
        doc_id=doc_id,
        file_id=file_id,
        max_chars=max_chars,
        embeddings=embeddings,
    )
