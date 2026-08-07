"""Generate the deterministic 100-query public Phase 1 judgment fixture."""

from __future__ import annotations

import json
from pathlib import Path


CLASSES = (
    ("direct_lookup", "What preserves source evidence?", ["event-ledger"]),
    ("dependency", "What does local retrieval depend on?", ["dependency-storage"]),
    ("contradiction", "What changed about inferred relations?", ["contradiction-old", "contradiction-new"]),
    ("chronology", "What happened on 2025-06-01?", ["chronology-second"]),
    ("navigation", "How are navigation summaries grounded?", ["navigation"]),
    ("out_of_scope", "What is the weather on Mars?", []),
)


def main() -> None:
    judgments = []
    for index in range(100):
        query_class, query, gold_record_ids = CLASSES[index % len(CLASSES)]
        judgments.append(
            {
                "id": f"public-{index + 1:03d}",
                "query": query,
                "query_class": query_class,
                "gold_record_ids": gold_record_ids,
                "notes": "Synthetic frozen public fixture.",
            }
        )
    target = Path(__file__).with_name("public-judged-queries.json")
    target.write_text(json.dumps({"schema_version": 1, "judged_queries": judgments}, indent=2) + "\n", encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
