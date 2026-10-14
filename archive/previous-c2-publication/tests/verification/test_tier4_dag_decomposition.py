"""Verification Suite 3: Tier 4 HyDE & Algorithmic DAG Query Decomposition Verification.

Scope:
1. Cyclic Dependency Handling:
   - Tarjan SCC / Kahn topological validation on decomposed sub-queries.
   - Self-loops (q1 -> q1), direct cycles (q1 -> q2 -> q1), indirect cycles (q1 -> q2 -> q3 -> q1).
   - Fail-closed error signaling under CAP-D011: CYCLIC_DEPENDENCY_DETECTED.
2. Hard Step Cap:
   - Enforce maximum decomposition depth K <= 4.
   - Adversarial queries attempting K > 4 expansions must be clamped or rejected.
3. Timeout Budget Enforcement:
   - SLA ceiling: <= 800ms.
   - Global timeout watchdog at 650ms during multi-hop DAG unrolling.
   - Verify graceful abort when sub-query execution stalls, returning bounded grounded candidates.
4. Early Abstention on Intermediate Hop Failure:
   - If hop k fails conformal non-conformity (s(q_k, D_k) > q_hat), immediately halt and emit
     ABSTAIN_INTERMEDIATE_HOP_UNRESOLVED, skipping subsequent hops.
"""

import time
import unittest
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class SubQueryNode:
    id: str
    query_text: str
    dependencies: List[str] = field(default_factory=list)  # IDs of nodes this node depends on


class DAGValidationError(Exception):
    pass


class CyclicDependencyError(DAGValidationError):
    pass


class StepCapExceededError(DAGValidationError):
    pass


class TimeoutWatchdogError(Exception):
    pass


@dataclass
class ExecutionResult:
    status: str
    completed_hops: int
    elapsed_ms: float
    grounded_evidence: List[str]
    error_code: Optional[str] = None


class Tier4DAGExecutor:
    """Simulates Tier 4 DAG Query Decomposition engine per RFC-003 Sections 3.4 & 8.2."""

    def __init__(
        self,
        max_hops: int = 4,
        sla_timeout_ms: float = 800.0,
        watchdog_timeout_ms: float = 650.0,
        conformal_q_hat: float = 0.45,
    ):
        self.max_hops = max_hops
        self.sla_timeout_ms = sla_timeout_ms
        self.watchdog_timeout_ms = watchdog_timeout_ms
        self.conformal_q_hat = conformal_q_hat

    def validate_and_sort(self, nodes: List[SubQueryNode]) -> List[SubQueryNode]:
        """Validates DAG constraints: K <= max_hops, no self-loops, no cycles."""
        # 1. Step cap enforcement
        if len(nodes) > self.max_hops:
            raise StepCapExceededError(f"Decomposition exceeded max depth: {len(nodes)} > {self.max_hops}")

        node_map = {n.id: n for n in nodes}
        in_degree = {n.id: 0 for n in nodes}
        adj = {n.id: [] for n in nodes}

        # Check self loops and build adjacency
        for n in nodes:
            for dep in n.dependencies:
                if dep == n.id:
                    raise CyclicDependencyError(f"Self-loop detected on node '{n.id}'")
                if dep not in node_map:
                    raise DAGValidationError(f"Unresolved dependency: '{dep}'")
                # dep must execute BEFORE n: edge is dep -> n
                adj[dep].append(n.id)
                in_degree[n.id] += 1

        # Kahn's algorithm for topological sorting and cycle detection
        queue = deque([n.id for n in nodes if in_degree[n.id] == 0])
        ordered_ids = []

        while queue:
            curr = queue.popleft()
            ordered_ids.append(curr)
            for neighbor in adj[curr]:
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        if len(ordered_ids) != len(nodes):
            raise CyclicDependencyError(
                f"Cyclic dependency detected in query decomposition DAG (processed {len(ordered_ids)} of {len(nodes)})"
            )

        return [node_map[nid] for nid in ordered_ids]

    def execute_dag(
        self,
        nodes: List[SubQueryNode],
        simulated_hop_latencies_ms: Dict[str, float],
        simulated_hop_conformities: Dict[str, float],
    ) -> ExecutionResult:
        """Executes validated DAG with SLA budget and early conformal abstention guards."""
        start_time = time.perf_counter()

        # Step 1: Validation
        try:
            ordered_nodes = self.validate_and_sort(nodes)
        except CyclicDependencyError as exc:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return ExecutionResult(
                status="FAIL_CLOSED",
                completed_hops=0,
                elapsed_ms=elapsed,
                grounded_evidence=[],
                error_code="CAP_D011_CYCLIC_DEPENDENCY_DETECTED"
            )
        except StepCapExceededError as exc:
            elapsed = (time.perf_counter() - start_time) * 1000.0
            return ExecutionResult(
                status="FAIL_CLOSED",
                completed_hops=0,
                elapsed_ms=elapsed,
                grounded_evidence=[],
                error_code="CAP_D011_STEP_CAP_EXCEEDED"
            )

        grounded = []
        completed = 0

        # Step 2: Stepwise execution
        for node in ordered_nodes:
            # Check watchdog
            now_ms = (time.perf_counter() - start_time) * 1000.0
            if now_ms >= self.watchdog_timeout_ms:
                # Watchdog aborts execution
                return ExecutionResult(
                    status="TIMEOUT_WATCHDOG_TRIGGERED",
                    completed_hops=completed,
                    elapsed_ms=now_ms,
                    grounded_evidence=grounded,
                    error_code="WATCHDOG_650MS_EXCEEDED"
                )

            # Simulate sub-query execution
            hop_latency = simulated_hop_latencies_ms.get(node.id, 50.0)
            time.sleep(hop_latency / 1000.0)
            completed += 1

            # Check conformal score for intermediate hop
            conf_score = simulated_hop_conformities.get(node.id, 0.20)
            if conf_score > self.conformal_q_hat:
                # Intermediate hop unresolved -> HALT IMMEDIATELY
                elapsed = (time.perf_counter() - start_time) * 1000.0
                return ExecutionResult(
                    status="ABSTAIN_INTERMEDIATE_HOP_UNRESOLVED",
                    completed_hops=completed,
                    elapsed_ms=elapsed,
                    grounded_evidence=grounded,
                    error_code=f"CONFORMAL_REJECTION_ON_{node.id}"
                )

            grounded.append(f"Evidence_for_{node.id}")

        total_elapsed = (time.perf_counter() - start_time) * 1000.0
        return ExecutionResult(
            status="SUCCESS",
            completed_hops=completed,
            elapsed_ms=total_elapsed,
            grounded_evidence=grounded,
            error_code=None
        )


class TestTier4DAGDecompositionVerification(unittest.TestCase):
    """Empirical verification of Tier 4 DAG Query Decomposition engine."""

    def setUp(self):
        self.executor = Tier4DAGExecutor(
            max_hops=4,
            sla_timeout_ms=800.0,
            watchdog_timeout_ms=650.0,
            conformal_q_hat=0.45
        )

    def test_cyclic_dependency_rejection_fail_closed(self):
        """Verify cyclic DAG decompositions fail-closed immediately with explicit error code."""
        # 1. Direct cycle: q1 -> q2 -> q1
        direct_cycle = [
            SubQueryNode(id="q1", query_text="Who founded Company X?", dependencies=["q2"]),
            SubQueryNode(id="q2", query_text="What was the founder's alma mater?", dependencies=["q1"]),
        ]
        res1 = self.executor.execute_dag(direct_cycle, {}, {})
        self.assertEqual(res1.status, "FAIL_CLOSED")
        self.assertEqual(res1.error_code, "CAP_D011_CYCLIC_DEPENDENCY_DETECTED")
        self.assertLess(res1.elapsed_ms, 50.0)

        # 2. Self-loop: q1 -> q1
        self_loop = [
            SubQueryNode(id="q1", query_text="Recursive self-dependency", dependencies=["q1"]),
        ]
        res2 = self.executor.execute_dag(self_loop, {}, {})
        self.assertEqual(res2.status, "FAIL_CLOSED")
        self.assertEqual(res2.error_code, "CAP_D011_CYCLIC_DEPENDENCY_DETECTED")

        # 3. 3-node cycle: q1 -> q2 -> q3 -> q1
        tri_cycle = [
            SubQueryNode(id="q1", query_text="A", dependencies=[]),
            SubQueryNode(id="q2", query_text="B", dependencies=["q1", "q3"]),
            SubQueryNode(id="q3", query_text="C", dependencies=["q2"]),
        ]
        res3 = self.executor.execute_dag(tri_cycle, {}, {})
        self.assertEqual(res3.status, "FAIL_CLOSED")
        self.assertEqual(res3.error_code, "CAP_D011_CYCLIC_DEPENDENCY_DETECTED")
        print("\n[DAG Cycle Rejection] All cyclic topologies caught and failed-closed under CAP-D011.")

    def test_hard_step_cap_enforcement(self):
        """Verify that decompositions with K > 4 are rejected fail-closed."""
        over_depth = [
            SubQueryNode(id=f"q{i}", query_text=f"Hop {i}", dependencies=[f"q{i-1}"] if i > 1 else [])
            for i in range(1, 6)  # K = 5 hops
        ]
        res = self.executor.execute_dag(over_depth, {}, {})
        self.assertEqual(res.status, "FAIL_CLOSED")
        self.assertEqual(res.error_code, "CAP_D011_STEP_CAP_EXCEEDED")
        print("[DAG Step Cap] Queries with K > 4 strictly rejected.")

    def test_timeout_watchdog_enforcement_under_sla(self):
        """Verify watchdog aborts execution at 650ms, preserving <= 800ms SLA."""
        # 3-hop query where each hop is sluggish (e.g. 250ms each)
        # Hop 1: 250ms (total 250ms)
        # Hop 2: 250ms (total 500ms)
        # Hop 3: Before start, now_ms ~ 500ms. If watchdog is 650ms, Hop 3 starts.
        # But if Hop 1 is 350ms, Hop 2 is 350ms -> 700ms > 650ms watchdog -> terminates!
        sluggish_dag = [
            SubQueryNode(id="q1", query_text="Hop 1", dependencies=[]),
            SubQueryNode(id="q2", query_text="Hop 2", dependencies=["q1"]),
            SubQueryNode(id="q3", query_text="Hop 3", dependencies=["q2"]),
        ]
        latencies = {
            "q1": 350.0,
            "q2": 350.0,
            "q3": 300.0,
        }
        res = self.executor.execute_dag(sluggish_dag, latencies, {})

        print(f"\n[Timeout Watchdog] Status: {res.status}, Completed Hops: {res.completed_hops}, Elapsed: {res.elapsed_ms:.1f}ms")
        self.assertEqual(res.status, "TIMEOUT_WATCHDOG_TRIGGERED")
        self.assertEqual(res.error_code, "WATCHDOG_650MS_EXCEEDED")
        self.assertEqual(res.completed_hops, 2)  # Hop 1 and 2 ran, Hop 3 blocked by watchdog
        self.assertLessEqual(res.elapsed_ms, 800.0, "Total execution exceeded 800ms SLA ceiling!")

    def test_early_abstention_on_unresolved_intermediate_hop(self):
        """Verify that when intermediate hop fails conformal threshold, execution halts immediately."""
        chain_dag = [
            SubQueryNode(id="q1", query_text="Root hop", dependencies=[]),
            SubQueryNode(id="q2", query_text="Dependent hop", dependencies=["q1"]),
            SubQueryNode(id="q3", query_text="Final hop", dependencies=["q2"]),
        ]
        conformities = {
            "q1": 0.20,  # <= 0.45 -> Valid
            "q2": 0.75,  # > 0.45 -> UNRESOLVED!
            "q3": 0.10,  # Should never be reached
        }
        latencies = {"q1": 20.0, "q2": 20.0, "q3": 20.0}

        res = self.executor.execute_dag(chain_dag, latencies, conformities)
        print(f"\n[Early Abstention] Status: {res.status}, Completed: {res.completed_hops}, Code: {res.error_code}")
        self.assertEqual(res.status, "ABSTAIN_INTERMEDIATE_HOP_UNRESOLVED")
        self.assertEqual(res.completed_hops, 2)  # Halted at q2, q3 never attempted
        self.assertEqual(len(res.grounded_evidence), 1)  # Only q1 evidence retained


if __name__ == "__main__":
    unittest.main()
