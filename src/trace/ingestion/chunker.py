import numpy as np
import json
from sklearn.feature_extraction.text import CountVectorizer
from sentence_transformers import SentenceTransformer
from typing import List, Tuple
import nltk
from nltk.tokenize import sent_tokenize
from transformers import pipeline
import torch

CANDIDATE_LABELS = [
    'core architectural constraint', 
    'hypothesis or proposal', 
    'example or analogy', 
    'ephemeral or temporary thought', 
    'background context'
]

LABEL_TO_TAG = {
    'core architectural constraint': 'core_concept',
    'hypothesis or proposal': 'hypothesis',
    'example or analogy': 'example',
    'ephemeral or temporary thought': 'ephemeral',
    'background context': 'background'
}
# Ensure nltk punkt is downloaded
try:
    nltk.data.find('tokenizers/punkt')
except LookupError:
    nltk.download('punkt', quiet=True)
try:
    nltk.data.find('tokenizers/punkt_tab')
except LookupError:
    nltk.download('punkt_tab', quiet=True)


class SemanticChunker:
    def __init__(self, model_name: str = 'all-MiniLM-L6-v2', similarity_threshold: float = 0.5):
        self.model = SentenceTransformer(model_name)
        self.similarity_threshold = similarity_threshold
        # Using CountVectorizer to extract raw term frequencies for the sparse vector.
        # This allows accurate BM25/TF-IDF calculation later during the merge phase.
        self.vectorizer = CountVectorizer(stop_words='english')
        # Initialize zero-shot classifier for structural tagging
        device = 0 if torch.cuda.is_available() else -1
        self.classifier = pipeline("zero-shot-classification", model="facebook/bart-large-mnli", device=device)

    def chunk_text(self, text: str) -> List[Tuple[str, str, str]]:
        """
        Chunks text semantically based on cosine similarity of adjacent sentences.
        Returns a list of tuples: (chunk_text, sparse_vector_json, structural_tag)
        """
        # Split into paragraphs to maintain structural boundaries, then sentences
        paragraphs = [p.strip() for p in text.split('\n\n') if p.strip()]
        
        sentences = []
        for p in paragraphs:
            sents = sent_tokenize(p)
            sentences.extend(sents)
            
        if not sentences:
            return []

        # Generate dense embeddings for all sentences
        embeddings = self.model.encode(sentences)
        
        chunks = []
        current_chunk = [sentences[0]]
        
        # EMA for Event Segmentation
        alpha = 0.5
        event_ema = embeddings[0]
        
        for i in range(1, len(sentences)):
            emb = embeddings[i]
            
            norm_ema = np.linalg.norm(event_ema)
            norm_emb = np.linalg.norm(emb)
            
            if norm_ema == 0 or norm_emb == 0:
                similarity = 0
            else:
                similarity = np.dot(event_ema, emb) / (norm_ema * norm_emb)
            
            # Group into the same chunk if it belongs to the current event
            if similarity >= self.similarity_threshold:
                current_chunk.append(sentences[i])
                event_ema = alpha * emb + (1 - alpha) * event_ema
            else:
                chunks.append(" ".join(current_chunk))
                current_chunk = [sentences[i]]
                event_ema = emb
                
        if current_chunk:
            chunks.append(" ".join(current_chunk))
            
        if not chunks:
            return []
            
        # Thalamic Filter
        filtered_chunks = []
        for c in chunks:
            words = c.split()
            if len(words) > 10:
                filtered_chunks.append(c)
        chunks = filtered_chunks
        
        if not chunks:
            return []
            
        # Compute sparse representations (Term Frequencies)
        try:
            X = self.vectorizer.fit_transform(chunks)
            vocab = self.vectorizer.get_feature_names_out()
            
            results = []
            for i in range(len(chunks)):
                # Extract non-zero term frequencies
                row = X.getrow(i)
                sparse_dict = {}
                for col_idx, count in zip(row.indices, row.data):
                    term = vocab[col_idx]
                    # Convert to int, not numpy.int64 to ensure JSON serializability
                    sparse_dict[term] = int(count)
                    
                sparse_json = json.dumps(sparse_dict)
                
                # Run zero-shot classification to determine the structural tag
                try:
                    result = self.classifier(chunks[i], CANDIDATE_LABELS, multi_label=False)
                    top_label = result['labels'][0]
                    top_score = result['scores'][0]
                    
                    if top_score > 0.4:
                        structural_tag = LABEL_TO_TAG.get(top_label, 'core_concept')
                    else:
                        structural_tag = 'core_concept'
                except Exception as e:
                    print(f"Classifier error: {e}")
                    structural_tag = 'core_concept'
                    
                results.append((chunks[i], sparse_json, structural_tag))
                
            return results
        except ValueError:
            # E.g. when text only contains stop words and vocab is empty
            return [(c, "{}", "core_concept") for c in chunks]

# Global instance
semantic_chunker = SemanticChunker()
