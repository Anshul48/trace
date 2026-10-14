"""TL GPU encode stage + CPU consumption harness.

Modules:
  config   pinned encoder spec + cache-key derivation
  chunking import-only access to the frozen tlsys chunker
  cache    incremental file-backed embedding cache (stdlib-only)
  encode   GPU encode stage (torch/ST imported lazily; CUDA on host only)
  consume  CPU-side file-backed emb() for ingest_docs
  drift    numeric-drift + threshold-sensitivity gates (no allclose)
  run_gpu_encode      CLI entry point for the Windows run
  export_sample_docs  sample-doc exporter from authorized sources
  harness_check       synthetic end-to-end harness verification
"""
