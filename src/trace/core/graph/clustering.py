import numpy as np
import json
from typing import List, Dict, Set
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from trace.core.schemas import HippocampalTrace

class GraphClusterer:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", base_distance_threshold: float = 0.5):
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(model_name, device=device)
        self.base_distance_threshold = base_distance_threshold
        self.max_island_size = 15

    def get_islands(self, traces: List[HippocampalTrace], blocks_dict: Dict[str, dict]) -> List[List[HippocampalTrace]]:
        if not traces:
            return []
            
        return self._shatter_islands(traces, blocks_dict, self.base_distance_threshold)

    def _shatter_islands(self, traces: List[HippocampalTrace], blocks_dict: Dict[str, dict], threshold: float) -> List[List[HippocampalTrace]]:
        if len(traces) <= 1:
            return [traces]
            
        n = len(traces)
        
        # 1. Dense Distance Matrix
        anchors = [t.anchor_concept for t in traces]
        embeddings = self.model.encode(anchors)
        # Cosine distance: 1 - cosine similarity
        norm_emb = embeddings / (np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-9)
        dense_sim = np.dot(norm_emb, norm_emb.T)
        dense_dist = np.clip(1.0 - dense_sim, 0.0, 1.0)
        
        # 2. Sparse Distance Matrix (Jaccard similarity of terms)
        sparse_dist = np.ones((n, n), dtype=float)
        trace_terms = []
        for t in traces:
            terms = set()
            if t.source_meta and t.source_meta.block_id:
                block = blocks_dict.get(t.source_meta.block_id)
                if block and block.get("sparse_vector"):
                    try:
                        sv = json.loads(block["sparse_vector"])
                        terms = set(sv.keys())
                    except:
                        pass
            trace_terms.append(terms)
            
        for i in range(n):
            for j in range(i, n):
                if i == j:
                    sparse_dist[i, j] = 0.0
                else:
                    set_i = trace_terms[i]
                    set_j = trace_terms[j]
                    if not set_i and not set_j:
                        dist = 1.0
                    else:
                        intersection = len(set_i.intersection(set_j))
                        union = len(set_i.union(set_j))
                        jaccard_sim = intersection / union if union > 0 else 0.0
                        dist = 1.0 - jaccard_sim
                    sparse_dist[i, j] = dist
                    sparse_dist[j, i] = dist
                    
        # 3. Graph Adjacency Matrix
        graph_dist = np.ones((n, n), dtype=float)
        np.fill_diagonal(graph_dist, 0.0)
        
        # Map anchor concepts to indices for edge resolution
        anchor_to_idx = {}
        for i, t in enumerate(traces):
            if t.anchor_concept not in anchor_to_idx:
                anchor_to_idx[t.anchor_concept] = []
            anchor_to_idx[t.anchor_concept].append(i)
            
        for i, t in enumerate(traces):
            for rel in t.relations:
                target = rel.target_concept
                # Substring match fallback
                target_indices = anchor_to_idx.get(target, [])
                if not target_indices:
                    for a_name, indices in anchor_to_idx.items():
                        if target.lower() in a_name.lower():
                            target_indices = indices
                            break
                for j in target_indices:
                    if i != j:
                        graph_dist[i, j] = 0.0  # Connected = 0 distance
                        graph_dist[j, i] = 0.0
                        
        # Combine: 60% Dense, 20% Sparse, 20% Graph
        hybrid_dist = 0.6 * dense_dist + 0.2 * sparse_dist + 0.2 * graph_dist
        
        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=threshold,
            metric="precomputed",
            linkage="average"
        )
        labels = clustering.fit_predict(hybrid_dist)
        
        clusters = {}
        for idx, label in enumerate(labels):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(traces[idx])
            
        final_islands = []
        for label, group in clusters.items():
            # Handle potential infinite recursion if all elements are identical
            if len(group) == n and len(group) > self.max_island_size:
                 # Force split if they can't be separated by threshold
                 mid = len(group) // 2
                 final_islands.append(group[:mid])
                 final_islands.append(group[mid:])
            elif len(group) > self.max_island_size:
                # Recursive shatter with tighter threshold (lower distance required)
                shattered = self._shatter_islands(group, blocks_dict, threshold * 0.8)
                final_islands.extend(shattered)
            else:
                final_islands.append(group)
                
        return final_islands
