from typing import List, Dict
import torch
import transformers
from sentence_transformers import SentenceTransformer
from sklearn.cluster import AgglomerativeClustering
from trace.core.schemas import HippocampalTrace, CanonicalEntity

class GraphClusterer:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2", distance_threshold: float = 0.5):
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(model_name, device=device)
        self.distance_threshold = distance_threshold

    def cluster_traces(self, traces: List[HippocampalTrace]) -> List[CanonicalEntity]:
        if not traces:
            return []
        
        # Extract unique anchors and map them to traces
        anchor_to_traces = {}
        for t in traces:
            if t.anchor_concept not in anchor_to_traces:
                anchor_to_traces[t.anchor_concept] = []
            anchor_to_traces[t.anchor_concept].append(t)
            
        unique_anchors = list(anchor_to_traces.keys())
        
        if len(unique_anchors) == 1:
            canonical_name = unique_anchors[0]
            entity = CanonicalEntity(
                id=canonical_name.lower().replace(" ", "_"),
                canonical_name=canonical_name,
                traces=anchor_to_traces[canonical_name],
                status=anchor_to_traces[canonical_name][-1].status
            )
            return [entity]
            
        embeddings = self.model.encode(unique_anchors)
        
        clustering = AgglomerativeClustering(
            n_clusters=None,
            distance_threshold=self.distance_threshold,
            metric="cosine",
            linkage="average"
        )
        labels = clustering.fit_predict(embeddings)
        
        clusters: Dict[int, List[str]] = {}
        for label, anchor in zip(labels, unique_anchors):
            if label not in clusters:
                clusters[label] = []
            clusters[label].append(anchor)
            
        canonical_entities = []
        for label, group in clusters.items():
            # Simple canonical name logic
            canonical_name = min(group, key=len)
            c_id = canonical_name.lower().replace(" ", "_").replace("-", "_")
            
            group_traces = []
            for anchor in group:
                group_traces.extend(anchor_to_traces[anchor])
                
            # Chronological sort (approximate) to get final status
            group_traces.sort(key=lambda t: t.source_meta.chunk_index if t.source_meta else 0)
            status = group_traces[-1].status if group_traces else "informational"
            
            canonical_entities.append(CanonicalEntity(
                id=c_id,
                canonical_name=canonical_name,
                traces=group_traces,
                status=status
            ))
            
        return canonical_entities
