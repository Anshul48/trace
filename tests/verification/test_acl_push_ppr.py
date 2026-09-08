"""Verification Suite 1: Andersen-Chung-Lang (ACL) Forward Push-PPR Empirical Verification.

Scope:
1. Verify theoretical bound: Total pushes <= 1 / (alpha * (1 - alpha) * epsilon).
2. Stress-test on synthetic graphs:
   - Sparse random graphs (Erdos-Renyi / random regular)
   - Power-law / scale-free networks (Barabasi-Albert)
   - Dense hub graphs (star graphs with degree 1,000 - 50,000)
3. Verify wall-clock time and active set size are independent of global |V| (1k to 1M nodes).
4. Verify numerical stability and probability mass conservation (sum p + sum r == 1.0).
5. Adversarial audit of RFC-004 Kernel 2:
   - Dangling node mass leakage bug (RFC-004 lines 668-670 drops alpha*res without teleporting to seeds).
   - Global O(N) allocation and linear scan flaw (RFC-004 lines 637-640, 688-694).
"""

import math
import random
import time
import unittest
from typing import Dict, List, Tuple


class CSRGraph:
    """Memory-efficient Compressed Sparse Row representation using Python arrays."""
    def __init__(self, num_nodes: int, row_ptr: List[int], col_indices: List[int], weights: List[float]):
        self.num_nodes = num_nodes
        self.row_ptr = row_ptr
        self.col_indices = col_indices
        self.weights = weights
        self.out_degrees = [row_ptr[i + 1] - row_ptr[i] for i in range(num_nodes)]


def generate_sparse_random_graph(num_nodes: int, avg_degree: int = 10, seed: int = 42) -> CSRGraph:
    rng = random.Random(seed)
    row_ptr = [0]
    col_indices = []
    weights = []

    for u in range(num_nodes):
        deg = rng.randint(max(1, avg_degree - 4), avg_degree + 4)
        targets = set()
        for _ in range(deg):
            v = rng.randint(0, num_nodes - 1)
            if v != u:
                targets.add(v)
        for v in targets:
            col_indices.append(v)
            weights.append(1.0)
        row_ptr.append(len(col_indices))

    return CSRGraph(num_nodes, row_ptr, col_indices, weights)


def generate_power_law_graph(num_nodes: int, m: int = 5, seed: int = 42) -> CSRGraph:
    """Scale-free network generated via Barabasi-Albert preferential attachment."""
    rng = random.Random(seed)
    # Start with a small clique of m0 = m + 1 nodes
    m0 = m + 1
    adj = {i: set(j for j in range(m0) if j != i) for i in range(m0)}
    repeated_nodes = []
    for i in range(m0):
        repeated_nodes.extend([i] * len(adj[i]))

    for u in range(m0, num_nodes):
        adj[u] = set()
        targets = set()
        attempts = 0
        while len(targets) < m and attempts < 100:
            target = rng.choice(repeated_nodes)
            if target != u and target not in targets:
                targets.add(target)
            attempts += 1
        # Fallback if needed
        while len(targets) < m:
            t = rng.randint(0, u - 1)
            targets.add(t)

        adj[u].update(targets)
        for v in targets:
            adj[v].add(u)
        repeated_nodes.extend(list(targets))
        repeated_nodes.extend([u] * len(targets))

    # Convert to CSR
    row_ptr = [0]
    col_indices = []
    weights = []
    for u in range(num_nodes):
        for v in sorted(adj[u]):
            col_indices.append(v)
            weights.append(1.0)
        row_ptr.append(len(col_indices))

    return CSRGraph(num_nodes, row_ptr, col_indices, weights)


def generate_dense_hub_graph(num_nodes: int, hub_degree: int = 10000, seed: int = 42) -> CSRGraph:
    """Graph with one mega-hub (node 0) connected to hub_degree nodes, others sparse."""
    rng = random.Random(seed)
    hub_degree = min(hub_degree, num_nodes - 1)
    adj = {i: set() for i in range(num_nodes)}

    # Hub connects to first hub_degree nodes
    for v in range(1, hub_degree + 1):
        adj[0].add(v)
        adj[v].add(0)

    # Some sparse cross links
    for u in range(1, num_nodes):
        if len(adj[u]) < 3:
            for _ in range(2):
                v = rng.randint(0, num_nodes - 1)
                if v != u:
                    adj[u].add(v)

    row_ptr = [0]
    col_indices = []
    weights = []
    for u in range(num_nodes):
        for v in sorted(adj[u]):
            col_indices.append(v)
            weights.append(1.0)
        row_ptr.append(len(col_indices))

    return CSRGraph(num_nodes, row_ptr, col_indices, weights)


def run_acl_forward_push(
    graph: CSRGraph,
    seeds: List[Tuple[int, float]],
    alpha: float = 0.85,
    epsilon: float = 1e-5,
    degree_normalized: bool = False,
    fix_dangling: bool = True,
) -> Tuple[Dict[int, float], Dict[int, float], int, float]:
    """
    Executes Andersen-Chung-Lang Forward Push PPR with exact tracking.
    Returns (p, r, total_pushes, elapsed_time).
    """
    p: Dict[int, float] = {}
    r: Dict[int, float] = {}
    queue: List[int] = []
    in_queue: set = set()

    total_seed_mass = sum(w for _, w in seeds)
    seed_dist = {u: w / total_seed_mass for u, w in seeds}

    for u, w in seed_dist.items():
        r[u] = w
        deg = graph.out_degrees[u]
        thresh = epsilon * max(1, deg) if degree_normalized else epsilon
        if w >= thresh:
            queue.append(u)
            in_queue.add(u)

    push_count = 0
    start_time = time.perf_counter()

    while queue:
        u = queue.pop(0)
        in_queue.remove(u)

        delta = r.get(u, 0.0)
        deg = graph.out_degrees[u]
        thresh = epsilon * max(1, deg) if degree_normalized else epsilon

        if delta < thresh:
            continue

        # Convert (1 - alpha) * delta to permanent PageRank
        p[u] = p.get(u, 0.0) + (1.0 - alpha) * delta
        r[u] = 0.0
        push_count += 1

        push_mass = alpha * delta

        if deg == 0:
            if fix_dangling:
                # Proper PageRank teleportation to seeds
                for s_node, s_mass in seed_dist.items():
                    new_r = r.get(s_node, 0.0) + push_mass * s_mass
                    r[s_node] = new_r
                    s_deg = graph.out_degrees[s_node]
                    s_thresh = epsilon * max(1, s_deg) if degree_normalized else epsilon
                    if new_r >= s_thresh and s_node not in in_queue:
                        queue.append(s_node)
                        in_queue.add(s_node)
            # If not fix_dangling (RFC-004 flaw), mass simply leaks!
            continue

        start_idx = graph.row_ptr[u]
        end_idx = graph.row_ptr[u + 1]
        per_neighbor = push_mass / deg

        for idx in range(start_idx, end_idx):
            v = graph.col_indices[idx]
            new_r = r.get(v, 0.0) + per_neighbor
            r[v] = new_r

            v_deg = graph.out_degrees[v]
            v_thresh = epsilon * max(1, v_deg) if degree_normalized else epsilon
            if new_r >= v_thresh and v not in in_queue:
                queue.append(v)
                in_queue.add(v)

    elapsed = time.perf_counter() - start_time
    return p, r, push_count, elapsed


class TestACLPushPPRVerification(unittest.TestCase):
    """Rigorous empirical tests for ACL Push-PPR claims."""

    def test_theoretical_push_bound_on_diverse_topologies(self):
        """Verify total pushes <= 1 / (alpha * (1 - alpha) * epsilon) across topologies."""
        alpha = 0.85
        epsilon = 1e-4  # Bound: 1 / (0.85 * 0.15 * 1e-4) = 78,431 pushes
        theoretical_max = int(1.0 / (alpha * (1.0 - alpha) * epsilon))

        # 1. Sparse random graph
        g_sparse = generate_sparse_random_graph(num_nodes=5000, avg_degree=8)
        _, _, pushes_sparse, _ = run_acl_forward_push(g_sparse, [(0, 1.0)], alpha=alpha, epsilon=epsilon)
        self.assertLessEqual(pushes_sparse, theoretical_max)

        # 2. Scale-free power law graph
        g_power = generate_power_law_graph(num_nodes=5000, m=4)
        _, _, pushes_power, _ = run_acl_forward_push(g_power, [(0, 1.0)], alpha=alpha, epsilon=epsilon)
        self.assertLessEqual(pushes_power, theoretical_max)

        # 3. Dense hub graph (node 0 has degree 4000)
        g_hub = generate_dense_hub_graph(num_nodes=5000, hub_degree=4000)
        _, _, pushes_hub_seed, _ = run_acl_forward_push(g_hub, [(0, 1.0)], alpha=alpha, epsilon=epsilon)
        self.assertLessEqual(pushes_hub_seed, theoretical_max)

        # Seed at peripheral node pointing into dense hub
        _, _, pushes_hub_periph, _ = run_acl_forward_push(g_hub, [(10, 1.0)], alpha=alpha, epsilon=epsilon)
        self.assertLessEqual(pushes_hub_periph, theoretical_max)

        print(f"\n[Push Bounds] Max Theoretical: {theoretical_max}")
        print(f"  Sparse: {pushes_sparse} pushes")
        print(f"  Power-Law: {pushes_power} pushes")
        print(f"  Dense Hub (seed=hub): {pushes_hub_seed} pushes")
        print(f"  Dense Hub (seed=leaf): {pushes_hub_periph} pushes")

    def test_independence_of_global_graph_size_v(self):
        """Verify wall time and active set size do NOT scale with global |V|."""
        sizes = [1000, 5000, 20000, 100000]
        alpha = 0.85
        epsilon = 1e-4

        results = []
        for n in sizes:
            g = generate_sparse_random_graph(num_nodes=n, avg_degree=10, seed=123)
            p, r, pushes, elapsed = run_acl_forward_push(g, [(0, 1.0)], alpha=alpha, epsilon=epsilon)
            num_activated = len(p)
            results.append((n, pushes, num_activated, elapsed))

        print("\n[Scale Independence Test (|V| vs Wall Time)]")
        for n, pushes, activated, elapsed in results:
            print(f"  |V| = {n:6d} -> Pushes: {pushes:5d}, Activated: {activated:5d}, Time: {elapsed*1000:6.2f} ms")

        # The ratio of time between |V|=1,000 and |V|=100,000 should NOT be 100x
        # Work is strictly local to the activated neighborhood!
        t_1k = results[0][3]
        t_100k = results[-1][3]
        self.assertLess(t_100k / max(1e-6, t_1k), 10.0, "Time scaled with |V|, violating local complexity!")

    def test_numerical_stability_and_mass_conservation(self):
        """Verify exact conservation invariant: sum(p) + sum(r) == 1.0."""
        g = generate_power_law_graph(num_nodes=2000, m=3)
        alpha = 0.85
        epsilon = 1e-5

        p, r, pushes, _ = run_acl_forward_push(g, [(0, 1.0)], alpha=alpha, epsilon=epsilon, fix_dangling=True)

        sum_p = sum(p.values())
        sum_r = sum(r.values())
        total_mass = sum_p + sum_r

        print(f"\n[Mass Conservation] sum(p)={sum_p:.6f}, sum(r)={sum_r:.6f}, Total={total_mass:.8f}")
        self.assertAlmostEqual(total_mass, 1.0, places=5, msg="Probability mass was not conserved!")

        # Verify no NaN or Inf
        for u, val in p.items():
            self.assertFalse(math.isnan(val) or math.isinf(val))
        for u, val in r.items():
            self.assertFalse(math.isnan(val) or math.isinf(val))

    def test_adversarial_rfc004_dangling_node_mass_leakage(self):
        """ADVERSARIAL: Prove that RFC-004 lines 668-670 leak probability mass when dangling nodes exist."""
        # Create a graph where node 0 points to node 1, but node 1 has 0 out-edges (dangling)
        g_dangling = CSRGraph(
            num_nodes=3,
            row_ptr=[0, 1, 1, 1],
            col_indices=[1],
            weights=[1.0]
        )

        # 1. Run with fix_dangling=False (RFC-004 implementation)
        p_flawed, r_flawed, _, _ = run_acl_forward_push(
            g_dangling, [(0, 1.0)], alpha=0.85, epsilon=1e-5, fix_dangling=False
        )
        total_flawed = sum(p_flawed.values()) + sum(r_flawed.values())
        print(f"\n[RFC-004 Dangling Leak Flaw] Total mass remaining: {total_flawed:.6f} (Expected: < 1.0 due to leakage)")
        # In RFC-004, node 1 gets alpha * 1.0 = 0.85 residual. When pushed, (1-alpha)*0.85 is p,
        # but the remaining alpha*(alpha*1.0) = 0.7225 is LOST because start==end has no neighbors!
        self.assertLess(total_flawed, 0.99, "RFC-004 failed to reproduce expected mass leakage bug!")

        # 2. Run with fix_dangling=True (Correct PageRank teleportation)
        p_fixed, r_fixed, _, _ = run_acl_forward_push(
            g_dangling, [(0, 1.0)], alpha=0.85, epsilon=1e-5, fix_dangling=True
        )
        total_fixed = sum(p_fixed.values()) + sum(r_fixed.values())
        self.assertAlmostEqual(total_fixed, 1.0, places=5, msg="Fixed version should conserve mass!")

    def test_adversarial_rfc004_dense_allocation_and_scan_overhead(self):
        """ADVERSARIAL: Prove that RFC-004 lines 637-640 (allocating Vec of size N) and lines 688-694 (O(N) loop)
        degrade wall-time with |V| even when active neighborhood is tiny."""
        alpha = 0.85
        epsilon = 1e-3

        # Simulate RFC-004 Rust dense array approach vs sparse dict approach
        def simulate_rfc004_dense_approach(num_nodes: int):
            t0 = time.perf_counter()
            # RFC-004 lines 637-640: allocate vectors of size num_nodes
            p = [0.0] * num_nodes
            r = [0.0] * num_nodes
            in_queue = [False] * num_nodes
            queue = [0]
            r[0] = 1.0
            in_queue[0] = True

            # Perform a few pushes (local work: e.g. 20 pushes)
            for _ in range(20):
                if not queue:
                    break
                u = queue.pop(0)
                in_queue[u] = False
                res = r[u]
                r[u] = 0.0
                p[u] += (1.0 - alpha) * res
                # Push to a couple local neighbors
                for v in [(u + 1) % num_nodes, (u + 2) % num_nodes]:
                    r[v] += (alpha * res) / 2.0
                    if r[v] >= epsilon and not in_queue[v]:
                        queue.append(v)
                        in_queue[v] = True

            # RFC-004 lines 688-694: Linear scan across all num_nodes to extract results!
            count = 0
            max_results = 20
            out_nodes = []
            for i in range(num_nodes):
                if p[i] > 0.0 and count < max_results:
                    out_nodes.append(i)
                    count += 1

            t1 = time.perf_counter()
            return t1 - t0

        def simulate_sparse_approach(num_nodes: int):
            t0 = time.perf_counter()
            p = {}
            r = {0: 1.0}
            queue = [0]
            in_queue = {0}

            for _ in range(20):
                if not queue:
                    break
                u = queue.pop(0)
                in_queue.remove(u)
                res = r[u]
                r[u] = 0.0
                p[u] = p.get(u, 0.0) + (1.0 - alpha) * res
                for v in [(u + 1) % num_nodes, (u + 2) % num_nodes]:
                    new_r = r.get(v, 0.0) + (alpha * res) / 2.0
                    r[v] = new_r
                    if new_r >= epsilon and v not in in_queue:
                        queue.append(v)
                        in_queue.add(v)

            # Output extraction only scans non-zero p entries:
            out_nodes = sorted(p.keys(), key=lambda k: p[k], reverse=True)[:20]
            t1 = time.perf_counter()
            return t1 - t0

        # Measure for N = 10,000 vs N = 1,000,000
        t_dense_small = simulate_rfc004_dense_approach(10_000)
        t_dense_large = simulate_rfc004_dense_approach(1_000_000)

        t_sparse_small = simulate_sparse_approach(10_000)
        t_sparse_large = simulate_sparse_approach(1_000_000)

        print("\n[RFC-004 Dense vs Sparse Architecture Audit]")
        print(f"  RFC-004 Dense Array: N=10k -> {t_dense_small*1000:.2f}ms | N=1M -> {t_dense_large*1000:.2f}ms (Slowdown: {t_dense_large/t_dense_small:.1f}x)")
        print(f"  Sparse Frontier:     N=10k -> {t_sparse_small*1000:.2f}ms | N=1M -> {t_sparse_large*1000:.2f}ms (Slowdown: {t_sparse_large/max(1e-6, t_sparse_small):.1f}x)")

        # The RFC-004 dense approach exhibits an O(N) slowdown due to allocation and scan
        self.assertGreater(t_dense_large / t_dense_small, 5.0, "RFC-004 dense approach failed to show O(N) bottleneck!")


if __name__ == "__main__":
    unittest.main()
