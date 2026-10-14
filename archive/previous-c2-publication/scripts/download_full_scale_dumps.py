#!/usr/bin/env python3
"""Download Full Massive Scale Corpora Dumps (Wikipedia Multi-Stream & Real Code Repositories).

Downloads:
1. Wikipedia Official Multistream Compressed Dumps (Wikimedia ~1.5 GB compressed / ~6 GB raw)
2. CPython & Rust Compiler Bare Git Trees (~5.7 GB of technical ASTs, diffs, issues)
3. Direct streaming into /mnt/c/Users/anshu/AppData/Local/trace-scale-data/
"""

import os
import sys
import subprocess
import urllib.request
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SCALE_ROOT = Path("/mnt/c/Users/anshu/AppData/Local/trace-scale-data")
WIKI_DIR = SCALE_ROOT / "wikipedia" / "dumps"
CODE_DIR = SCALE_ROOT / "code"
WIKI_DIR.mkdir(parents=True, exist_ok=True)
CODE_DIR.mkdir(parents=True, exist_ok=True)

# 1. Wikipedia Multistream Chunks from Wikimedia Official
WIKI_CHUNKS = [
    ("enwiki_chunk1.xml.bz2", "https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-pages-articles-multistream1.xml-p1p41242.bz2"),
    ("enwiki_chunk10.xml.bz2", "https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-pages-articles-multistream10.xml-p4045403p5399366.bz2"),
    ("enwiki_chunk12.xml.bz2", "https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-pages-articles-multistream12.xml-p7054860p8554859.bz2"),
]

def download_wiki_chunk(fname, url):
    dest = WIKI_DIR / fname
    if dest.exists() and dest.stat().st_size > 10 * 1024 * 1024:
        print(f"[Wiki Dump] ✓ {fname} already present ({dest.stat().st_size / (1024*1024):.1f} MB)")
        return f"{fname}: Present"
    print(f"[Wiki Dump] Downloading {fname} from Wikimedia ({url})...")
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers={"User-Agent": "TraceResearchScaleDownloader/2.0"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(dest, "wb") as f_out:
        while True:
            chunk = resp.read(1024 * 1024)
            if not chunk:
                break
            f_out.write(chunk)
    elapsed = time.perf_counter() - t0
    print(f"[Wiki Dump] ✓ Finished {fname} ({dest.stat().st_size / (1024*1024):.1f} MB in {elapsed:.1f}s)")
    return f"{fname}: {dest.stat().st_size / (1024*1024):.1f} MB"

# 2. Major Code Repositories (CPython & Rust)
CODE_REPOS = [
    ("cpython.git", "https://github.com/python/cpython.git"),
    ("rust.git", "https://github.com/rust-lang/rust.git"),
]

def clone_code_repo(repo_name, git_url):
    dest = CODE_DIR / repo_name
    if dest.exists() and (dest / "objects").exists():
        size = sum(f.stat().st_size for f in (dest / "objects").rglob("*") if f.is_file())
        if size > 10 * 1024 * 1024:
            print(f"[Code Repo] ✓ {repo_name} already present ({size / (1024*1024):.1f} MB)")
            return f"{repo_name}: Present"
    print(f"[Code Repo] Cloning {repo_name} from {git_url}...")
    t0 = time.perf_counter()
    cmd = ["git", "clone", "--bare", "--depth=15000", git_url, str(dest)]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    elapsed = time.perf_counter() - t0
    if res.returncode == 0:
        print(f"[Code Repo] ✓ Cloned {repo_name} in {elapsed:.1f}s!")
        return f"{repo_name}: Cloned in {elapsed:.1f}s"
    else:
        print(f"[Code Repo] ✗ Error on {repo_name}: {res.stderr.decode('utf-8')[:200]}")
        return f"{repo_name}: Error"

def main():
    print("=== HIGH-VOLUME SCALE CORPORA DOWNLOADER (Wikipedia Dumps + Code Repos) ===")
    tasks = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        for fname, url in WIKI_CHUNKS:
            tasks.append(executor.submit(download_wiki_chunk, fname, url))
        for repo_name, git_url in CODE_REPOS:
            tasks.append(executor.submit(clone_code_repo, repo_name, git_url))

        for future in as_completed(tasks):
            try:
                res = future.result()
                print(f"  -> Task Result: {res}")
            except Exception as e:
                print(f"  -> Task Exception: {e}")
    print("\n[ALL HIGH-VOLUME DUMPS & CODE REPOSITORIES COMPLETED!]")
    return 0

if __name__ == "__main__":
    sys.exit(main())
