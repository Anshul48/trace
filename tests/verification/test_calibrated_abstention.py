"""Verification Suite 2: Calibrated Abstention & Semantic Entropy Verification.

Scope:
1. Split Conformal Prediction:
   - Calibration with n = 1,000 queries at target error alpha = 0.01 (coverage 1 - alpha = 0.99).
   - Compute empirical conformal quantile q_hat = Quantile(ceil((n+1)*0.99)/n).
   - In-distribution test: verify empirical coverage >= 99.0%.
   - Stress-test extreme distribution shift & unanswerable contrast queries (MuSiQue style).
2. Semantic Entropy Estimation:
   - Sampling M = 5 reasoning traces per query.
   - Bidirectional NLI equivalence clustering (P(A->B) >= 0.85 and P(B->A) >= 0.85).
   - Calculate Shannon entropy SE(q) = - sum P(S_k) * ln P(S_k).
   - Test calibrated threshold gamma_reject = 0.35.
   - Verify >= 99% abstention on unanswerable/hallucinated queries.
   - Verify absence of false-positive collapse on valid paraphrased answers.
3. Adversarial Edge Cases:
   - Non-transitive NLI relations (A <-> B, B <-> C, but A </-> C).
   - Distribution shift breaking the exchangeability assumption of conformal prediction.
"""

import math
import random
import unittest
from typing import List, Set, Dict, Tuple


def compute_conformal_quantile(calibration_scores: List[float], alpha: float = 0.01) -> float:
    """Computes empirical conformal quantile per Angelopoulos & Bates (2021)."""
    n = len(calibration_scores)
    p = math.ceil((n + 1) * (1.0 - alpha)) / n
    p = min(1.0, p)
    sorted_scores = sorted(calibration_scores)
    idx = int(math.ceil(p * n)) - 1
    idx = max(0, min(n - 1, idx))
    return sorted_scores[idx]


def evaluate_conformal_decision(
    retrieval_scores: List[float],
    ppr_masses: List[float],
    q_hat: float,
    tau_mass: float = 0.15,
) -> Tuple[bool, List[int]]:
    """
    Evaluates whether retrieval non-conformity triggers abstention.
    retrieval_scores: non-conformity s(q, d) for candidate docs
    Returns (should_abstain, candidate_indices)
    """
    candidates = [i for i, s in enumerate(retrieval_scores) if s <= q_hat]
    if not candidates:
        return True, []  # Empty candidate set -> Abstain

    total_ppr = sum(ppr_masses[i] for i in candidates)
    if total_ppr < tau_mass:
        return True, candidates  # Insufficient mass -> Abstain

    return False, candidates


def cluster_nli_equivalence(
    samples: List[str],
    nli_matrix: List[List[float]],
    threshold: float = 0.85
) -> List[List[int]]:
    """
    Partitions M samples into semantic equivalence classes using bidirectional NLI.
    nli_matrix[i][j] is P_NLI(sample_i => sample_j).
    Bidirectional condition: P(i => j) >= threshold AND P(j => i) >= threshold.
    """
    m = len(samples)
    visited = set()
    clusters = []

    for i in range(m):
        if i in visited:
            continue
        cluster = [i]
        visited.add(i)
        for j in range(i + 1, m):
            if j not in visited:
                # Check bidirectional entailment with all members in the cluster (clique criterion)
                # or with cluster leader. Trace specifies bidirectional pairwise.
                if (nli_matrix[i][j] >= threshold) and (nli_matrix[j][i] >= threshold):
                    cluster.append(j)
                    visited.add(j)
        clusters.append(cluster)

    return clusters


def compute_semantic_entropy(clusters: List[List[int]], m: int) -> float:
    """Computes Shannon semantic entropy across cluster probability distribution."""
    entropy = 0.0
    for c in clusters:
        p_k = len(c) / float(m)
        if p_k > 0.0:
            entropy -= p_k * math.log(p_k)
    return entropy


class TestCalibratedAbstentionVerification(unittest.TestCase):
    """Empirical verification of Split Conformal Prediction and Semantic Entropy."""

    def test_split_conformal_finite_sample_coverage(self):
        """Verify Split Conformal guarantees empirical coverage >= 1 - alpha = 0.99 under exchangeability."""
        rng = random.Random(42)
        n_cal = 1000
        n_test = 5000
        alpha = 0.01

        # Simulate in-distribution non-conformity scores for true supporting document:
        # Most true supporting docs have low non-conformity score (e.g. Beta(1.5, 8.0))
        # yielding scores mostly in [0.05, 0.45] with rare tail up to 0.70.
        def sample_true_nonconformity():
            # Beta-like distribution scaled to [0.02, 0.65]
            val = rng.betavariate(1.5, 8.0)
            return min(1.0, max(0.0, val * 0.8 + 0.02))

        cal_scores = [sample_true_nonconformity() for _ in range(n_cal)]
        q_hat = compute_conformal_quantile(cal_scores, alpha=alpha)

        print(f"\n[Conformal Calibration] n_cal={n_cal}, alpha={alpha}, q_hat={q_hat:.4f}")

        # Test on fresh exchangeable test queries
        test_scores = [sample_true_nonconformity() for _ in range(n_test)]
        covered = sum(1 for s in test_scores if s <= q_hat)
        empirical_coverage = covered / float(n_test)
        empirical_error = 1.0 - empirical_coverage

        print(f"  In-Distribution Test (n={n_test}): Coverage={empirical_coverage*100:.2f}%, Error={empirical_error*100:.2f}%")
        self.assertGreaterEqual(
            empirical_coverage,
            0.985,  # Statistical tolerance around 0.99 for finite sample n=5000
            f"Conformal coverage violated! Expected >= 0.99, got {empirical_coverage}"
        )

    def test_unanswerable_contrast_questions_musique_abstention(self):
        """Stress-test unanswerable contrast questions where ground-truth atoms are missing."""
        rng = random.Random(123)
        n_contrast = 2000
        alpha = 0.01
        q_hat = 0.45  # Representative calibrated quantile
        tau_mass = 0.15

        abstained_count = 0
        for _ in range(n_contrast):
            # For unanswerable contrast questions, the true evidence does not exist in corpus.
            # The top retrieved spurious documents have high non-conformity scores (e.g., 0.60 to 0.98).
            # Also PPR mass on candidate set is dispersed (< 0.15).
            num_retrieved = 10
            retrieved_scores = [rng.uniform(0.52, 0.98) for _ in range(num_retrieved)]
            # Occasionally by random chance 1 spurious doc has score 0.42 (< q_hat)
            if rng.random() < 0.03:
                retrieved_scores[0] = rng.uniform(0.38, 0.44)

            # Spurious docs have tiny PPR diffusion mass
            ppr_masses = [rng.uniform(0.005, 0.02) for _ in range(num_retrieved)]

            should_abstain, _ = evaluate_conformal_decision(
                retrieved_scores, ppr_masses, q_hat, tau_mass=tau_mass
            )
            if should_abstain:
                abstained_count += 1

        abstention_rate = abstained_count / float(n_contrast)
        print(f"\n[Unanswerable Contrast Queries (MuSiQue)] Abstention Rate: {abstention_rate*100:.2f}% (Target: >= 99.0%)")
        self.assertGreaterEqual(
            abstention_rate,
            0.990,
            f"Failed to achieve >= 99% abstention on unanswerable contrast queries! Got {abstention_rate*100:.2f}%"
        )

    def test_semantic_entropy_certainty_vs_hallucination(self):
        """Verify Semantic Entropy cleanly discriminates consistent answers from hallucinations."""
        m = 5
        gamma_reject = 0.35

        # Case 1: Consistent ground-truth reasoning (5 paraphrased answers with high mutual entailment)
        # All NLI scores >= 0.95
        nli_certain = [[0.98 if i != j else 1.0 for j in range(m)] for i in range(m)]
        clusters_certain = cluster_nli_equivalence(["ans"] * m, nli_certain, threshold=0.85)
        se_certain = compute_semantic_entropy(clusters_certain, m)
        print(f"\n[Semantic Entropy] Grounded/Certain: SE={se_certain:.4f} (Rejection threshold: {gamma_reject})")
        self.assertEqual(len(clusters_certain), 1)
        self.assertEqual(se_certain, 0.0)
        self.assertLessEqual(se_certain, gamma_reject, "Consistent answers should not be rejected (no false positive)!")

        # Case 2: Catastrophic hallucination / divergent reasoning (5 mutually exclusive answers)
        # All cross NLI scores <= 0.10
        nli_divergent = [[0.05 if i != j else 1.0 for j in range(m)] for i in range(m)]
        clusters_divergent = cluster_nli_equivalence(["ans1", "ans2", "ans3", "ans4", "ans5"], nli_divergent, threshold=0.85)
        se_divergent = compute_semantic_entropy(clusters_divergent, m)
        print(f"  Hallucinatory/Divergent: SE={se_divergent:.4f} (Max ln(5)={math.log(5):.4f})")
        self.assertEqual(len(clusters_divergent), 5)
        self.assertAlmostEqual(se_divergent, math.log(5), places=4)
        self.assertGreater(se_divergent, gamma_reject, "Divergent answers must be rejected!")

        # Case 3: Partial ambiguity (3 agree on interpretation A, 2 agree on interpretation B)
        # Cluster 1: {0, 1, 2}, Cluster 2: {3, 4}
        nli_partial = [[1.0] * m for _ in range(m)]
        for i in range(m):
            for j in range(m):
                if (i in {0, 1, 2} and j in {3, 4}) or (i in {3, 4} and j in {0, 1, 2}):
                    nli_partial[i][j] = 0.05
                else:
                    nli_partial[i][j] = 0.95
        clusters_partial = cluster_nli_equivalence(["ans"] * m, nli_partial, threshold=0.85)
        se_partial = compute_semantic_entropy(clusters_partial, m)
        # P(A) = 3/5 = 0.6, P(B) = 2/5 = 0.4
        expected_se = -(0.6 * math.log(0.6) + 0.4 * math.log(0.4))
        print(f"  Partial Ambiguity (3/2 split): SE={se_partial:.4f} (Expected: {expected_se:.4f})")
        self.assertAlmostEqual(se_partial, expected_se, places=4)
        # Since expected_se = 0.673 > 0.35, partial ambiguity triggers safe abstention!
        self.assertGreater(se_partial, gamma_reject)

    def test_adversarial_distribution_shift_conformal_breakdown(self):
        """ADVERSARIAL: Evaluate Split Conformal when extreme distribution shift violates exchangeability."""
        rng = random.Random(999)
        n_cal = 1000
        alpha = 0.01

        # Calibration on standard in-domain distribution
        cal_scores = [rng.betavariate(1.5, 8.0) * 0.8 + 0.02 for _ in range(n_cal)]
        q_hat = compute_conformal_quantile(cal_scores, alpha=alpha)

        # Extreme covariate/domain shift: queries from an adversarial or novel domain
        # where non-conformity scores are systematically shifted higher by +0.25 (e.g. obscure math/code)
        shifted_test_scores = [min(1.0, (rng.betavariate(1.5, 8.0) * 0.8 + 0.02) + 0.25) for _ in range(5000)]
        covered = sum(1 for s in shifted_test_scores if s <= q_hat)
        shifted_coverage = covered / 5000.0

        print(f"\n[Adversarial Shift on Conformal Coverage] Standard q_hat={q_hat:.4f}")
        print(f"  Shifted Domain Coverage: {shifted_coverage*100:.2f}% (Dropped from 99%!)")

        # Under extreme shift, coverage drops significantly below 99% unless recalibrated.
        # This confirms RFC-003 Section 8.4 ("Calibration Drift under Domain Shifts & Online Recalibration")
        # is a real empirical vulnerability that requires online recalibration!
        self.assertLess(shifted_coverage, 0.90, "Expected conformal coverage collapse under uncalibrated shift!")

    def test_adversarial_intransitive_nli_clustering(self):
        """ADVERSARIAL: Test behavior when NLI model exhibits intransitivity: A <=> B and B <=> C, but A </=> C."""
        m = 3
        # A=0, B=1, C=2
        # P(0 <=> 1) = 0.90, P(1 <=> 2) = 0.90, but P(0 <=> 2) = 0.10
        nli_matrix = [
            [1.0, 0.90, 0.10],
            [0.90, 1.0, 0.90],
            [0.10, 0.90, 1.0],
        ]

        # Greedy first-come leader clustering:
        # Cluster 0 starts with 0 -> inspects 1 (matches) -> inspects 2 (doesn't match). Cluster 0: {0, 1}
        # Next unvisited is 2 -> Cluster 1: {2}. Total: 2 clusters.
        clusters = cluster_nli_equivalence(["A", "B", "C"], nli_matrix, threshold=0.85)
        se = compute_semantic_entropy(clusters, m)
        print(f"\n[Adversarial Intransitive NLI] Clusters: {clusters}, SE={se:.4f}")
        # Entropy is non-zero, triggering abstention on logically inconsistent/intransitive loops
        self.assertGreater(se, 0.0)


if __name__ == "__main__":
    unittest.main()
