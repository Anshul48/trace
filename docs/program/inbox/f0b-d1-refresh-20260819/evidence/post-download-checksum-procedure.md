# F0b Evidence — Post-Download Checksum and Verification Procedure

## 1. Staging Layout Specification

All admitted benchmark datasets must be staged in an approved external cache directory completely outside the Git repository tree, following the standard hierarchy:

```text
<benchmark-data-root>/ (e.g. C:\Users\anshu\.trace\benchmark_cache or external NVMe cache)
  downloads/
    <dataset-id>/
      <version-or-commit>/
        <raw-archive-or-files>
        download_receipt.json
  normalized/
    <dataset-id>/
      <transform-sha256>/
        corpus.jsonl
        queries.jsonl
        qrels.jsonl
        manifest.json
  logs/
    <dataset-id>/
      <acquisition-run-id>.log
```

---

## 2. Cryptographic Checksum Procedure

Every downloaded artifact must undergo mandatory post-download verification prior to normalization or evaluation:

### Step 1: Raw Archive Checksum
Immediately upon completing an HTTP/HTTPS stream download, compute the SHA-256 digest of the raw archive:

```python
import hashlib

def compute_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()
```

The resulting digest must match the expected archive hash recorded in the dataset admission record.

### Step 2: Content Normalization & Hash Verification
When extracting or transforming raw corpus text into `corpus.jsonl`:
1. Line endings must be normalized to standard Unix LF (`\n`).
2. Text encodings must be verified as valid UTF-8.
3. Compute the normalized corpus digest:
   ```python
   def compute_normalized_corpus_sha256(corpus_text: str) -> str:
       normalized = corpus_text.replace("\r\n", "\n")
       return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
   ```

### Step 3: Schema and Entity Reference Verification
Assert that every gold document ID in the query pack corresponds to an existing `doc_id` or `atom_id` in the corpus:
```python
missing_golds = [g_id for q in queries for g_id in q.gold_doc_ids if g_id not in corpus_doc_ids]
if missing_golds:
    raise DatasetIntegrityError(f"Found {len(missing_golds)} unresolvable gold document references!")
```

---

## 3. Strict Preflight Assertions

Before a staged dataset can be referenced by an `EVALUATION_MANIFEST`:
1. **No Partial Downloads**: If a download fails, times out, or receives HTTP 4xx/5xx, delete the `.download.tmp` file and fail closed.
2. **Strict TLS Enforcement**: All downloads must use `verify=True`. Never disable certificate verification.
3. **No Synthetic Fallback**: If the download fails, raise an explicit error. Never write a synthetic or sample JSON file to the cache.
4. **Admission Record Check**: Assert that `<dataset-id>` has an admitted record approved under decision P-001.
