#!/usr/bin/env python3
"""Measure pinned fff MCP behavior including pagination and exact-match loss."""

import argparse
import json
import os
from pathlib import Path
import random
import re
import shutil
import tempfile
import time
from mcp_client import Client, text_result

BASE = Path(__file__).resolve().parent


def make_client(corpus):
    out = BASE / "fff"
    prefix = [] if os.environ.get("SEARCH_BENCHMARK_OFFLINE") == "1" else [
        "/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)(deny network*)"
    ]
    cmd = prefix + [
        str(out / "fff-mcp"),
        "--no-update-check",
        "--no-watch",
        "--frecency-db",
        str(out / "mcp-frecency"),
        "--history-db",
        str(out / "mcp-history"),
        "--log-file",
        str(out / "mcp.log"),
        str(corpus),
    ]
    return Client(
        cmd,
        {"PATH": "/usr/bin:/bin"},
        str(corpus),
        out / "benchmark-mcp.stderr.txt",
    )


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repeats", type=int, default=7)
    a = p.parse_args()
    if a.repeats < 1:
        p.error("--repeats must be positive")
    paths = {
        f["path"] for f in json.loads((BASE / "manifest.json").read_text())["files"]
    }
    queries = json.loads((BASE / "queries.json").read_text())
    # fff MCP resolves a containing Git root. Copy outside this checkout so
    # the benchmark does not accidentally search the benchmark repository.
    temporary = tempfile.TemporaryDirectory(prefix="fff-corpus-", dir="/private/tmp")
    corpus = Path(temporary.name) / "corpus"
    shutil.copytree(BASE / "corpus", corpus)
    start = time.perf_counter()
    client = make_client(corpus)
    result = {
        "tool": "fff-mcp",
        "version": "0.11.0",
        "initialize_seconds": time.perf_counter() - start,
        "semantics": "smart-case + automatic fuzzy fallback, max 10 matches/file; not equivalent to exact grep",
        "trials": [],
    }
    rng = random.Random(617)
    try:
        for trial in range(-1, a.repeats):
            rng.shuffle(queries)
            for q in queries:
                start = time.perf_counter_ns()
                cursor = None
                seen_cursors = set()
                actual = set()
                size = 0
                pages = 0
                while True:
                    args = {"query": q["query"], "context": 1, "maxResults": 1000000}
                    if cursor:
                        args["cursor"] = cursor
                    text = text_result(client.call("grep", args))
                    size += len(text.encode())
                    pages += 1
                    current = None
                    for line in text.split("\n"):
                        candidate = re.split(r" \(| - | git:", line, maxsplit=1)[0]
                        if candidate in paths:
                            current = candidate
                        m = re.match(r"^\s+(\d+):", line)
                        if m and current:
                            actual.add((current, int(m[1])))
                    m = re.search(r"^cursor:\s*(\S+)", text, re.M)
                    if not m:
                        break
                    cursor = m[1]
                    if cursor in seen_cursors or pages > 10000:
                        raise RuntimeError("MCP cursor loop")
                    seen_cursors.add(cursor)
                elapsed = (time.perf_counter_ns() - start) / 1e6
                expected = {(x["path"], x["line"]) for x in q["expected"]}
                result["trials"].append(
                    {
                        "query_id": q["id"],
                        "trial": trial,
                        "milliseconds": elapsed,
                        "pages": pages,
                        "output_bytes": size,
                        "expected_count": len(expected),
                        "actual_count": len(actual),
                        "true_positive": len(actual & expected),
                        "false_positive": len(actual - expected),
                        "false_negative": len(expected - actual),
                        "exact": actual == expected,
                        "extra_examples": sorted(actual - expected)[:5],
                        "missing_examples": sorted(expected - actual)[:5],
                    }
                )
            (BASE / "fff/mcp-results.json").write_text(json.dumps(result, indent=2))
            print("fff MCP trial", trial, flush=True)
        for q in json.loads((BASE / "relationships.json").read_text()):
            text = text_result(
                client.call(
                    "grep",
                    {
                        "query": q["path"] + " " + q["symbol"],
                        "context": 40,
                        "maxResults": 1000,
                    },
                )
            )
            out = BASE / "qa-evidence/fff-mcp"
            out.mkdir(parents=True, exist_ok=True)
            (out / (q["id"] + ".txt")).write_text(text)
    finally:
        client.close()
        temporary.cleanup()


if __name__ == "__main__":
    main()
