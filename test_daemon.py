import asyncio
import sys
import os

# Ensure src is in python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), 'src')))

async def test_all():
    print("Loading SemanticChunker...")
    from trace.ingestion.chunker import semantic_chunker
    
    print("Testing SemanticChunker zero-shot classification...")
    test_text = "For example, consider a user who logs in. This is just an example."
    chunks = semantic_chunker.chunk_text(test_text)
    print("Chunker output:", chunks)
    
    print("Loading AttentionDaemon...")
    from trace.core.attention_daemon import attention_daemon
    
    print("Testing AttentionDaemon scoring...")
    score = attention_daemon._score_trace("Optimize database throughput", "We should replace ChromaDB with a faster local cache for vector similarity.", "")
    print(f"Attention score: {score}")
    
    print("All tests passed.")

if __name__ == "__main__":
    asyncio.run(test_all())
