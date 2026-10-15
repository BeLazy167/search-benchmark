#!/usr/bin/env python3
"""Small typo-tolerance smoke test, not a search-engine latency comparison."""

import json
from pathlib import Path
from fff_mcp_bench import make_client
from mcp_client import text_result

BASE = Path(__file__).resolve().parent
CASES = [
    ("stream-lifecyle.ts", "qbraid-api/src/features/ai/shared/stream-lifecycle.ts"),
    (
        "warm_pool_config_laoder.py",
        "jupyterhub-spawners/meta-spawner/meta_spawner/scripts/warm_pool_config_loader.py",
    ),
    ("linkify-job-qrnz.ts", "qbraid-account/src/lib/chat/linkify-job-qrns.ts"),
    (
        "payment-intent-faild.processor.ts",
        "worker-service/src/services/subscription/payment-intent-failed.processor.ts",
    ),
    (
        "useCanvsXL.ts",
        "qbraid-lab-extensions/src/features/dashboard/hooks/useCanvasXL.ts",
    ),
    (
        "drift-issue-manger.py",
        "qbraid-infrastructure/scripts/iac/drift-issue-manager.py",
    ),
]


def main():
    corpus_paths = {
        f["path"] for f in json.loads((BASE / "manifest.json").read_text())["files"]
    }
    client = make_client()
    rows = []
    try:
        for query, expected in CASES:
            assert expected in corpus_paths
            raw = text_result(
                client.call("find_files", {"query": query, "maxResults": 10})
            )
            paths = [
                line.split(" git:", 1)[0].split(" - ", 1)[0]
                for line in raw.splitlines()
            ]
            paths = [p for p in paths if p in corpus_paths]
            rows.append(
                {
                    "query": query,
                    "expected": expected,
                    "rank": paths.index(expected) + 1 if expected in paths else None,
                    "hit_at_10": expected in paths,
                    "returned_paths": paths,
                    "raw_response": raw,
                }
            )
    finally:
        client.close()
    (BASE / "fff/fuzzy-results.json").write_text(json.dumps(rows, indent=2) + "\n")
    print("fff typo filename hit@10", sum(r["hit_at_10"] for r in rows), "/", len(rows))


if __name__ == "__main__":
    main()
