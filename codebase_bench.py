#!/usr/bin/env python3
"""Isolated codebase-memory index and persistent MCP query benchmark."""

import argparse
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import time
from mcp_client import Client, text_result

BASE = Path(__file__).resolve().parent
BINARY = shutil.which("codebase-memory-mcp")


def main():
    if not BINARY:
        raise SystemExit("codebase-memory-mcp is required on PATH")
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--mode", choices=["full", "fast"], default="full")
    a = parser.parse_args()
    out = BASE / "codebase" / a.mode
    out.mkdir(parents=True, exist_ok=True)
    cache = out / "cache"
    cache.mkdir(exist_ok=True)
    env = {
        "PATH": "/usr/bin:/bin:/opt/homebrew/bin",
        "CBM_CACHE_DIR": str(cache),
        "XDG_CONFIG_HOME": str(out / "config"),
        "CBM_LSP_DISABLED": "1",
        "CBM_WORKERS": "4",
    }
    prefix = [
        "/usr/bin/sandbox-exec",
        "-p",
        "(version 1)(allow default)(deny network*)",
        BINARY,
    ]
    index_result = out / "index-result.json"
    if not index_result.exists():
        args = {"repo_path": str(BASE / "corpus"), "mode": a.mode, "persistence": False}
        cmd = prefix + ["cli", "index_repository", json.dumps(args)]
        start = time.perf_counter()
        p = subprocess.run(
            cmd, env=env, cwd=out, capture_output=True, text=True, timeout=600
        )
        row = {
            "seconds": time.perf_counter() - start,
            "returncode": p.returncode,
            "command": cmd,
            "env": env,
            "binary_sha256": hashlib.sha256(Path(BINARY).read_bytes()).hexdigest(),
        }
        (out / "index.stdout.txt").write_text(p.stdout)
        (out / "index.stderr.txt").write_text(p.stderr)
        index_result.write_text(json.dumps(row, indent=2))
        if p.returncode:
            raise RuntimeError("Index failed; inspect saved stderr")
        print("codebase index", row["seconds"], flush=True)
    project = json.loads((out / "index.stdout.txt").read_text())["project"]
    start = time.perf_counter()
    c = Client(prefix, env, str(out), out / "mcp.stderr.txt")
    result = {
        "tool": "codebase-memory-mcp",
        "version": "0.8.1",
        "mode": a.mode,
        "lsp": "disabled for offline AST comparison",
        "mcp_initialize_seconds": time.perf_counter() - start,
        "index": json.loads(index_result.read_text()),
        "trials": [],
    }
    tasks = [
        {"id": f"symbol-{i:02d}", "kind": "symbol", **q}
        for i, q in enumerate(json.loads((BASE / "symbols.json").read_text()))
    ]
    tasks += [
        {"kind": "callers", **q}
        for q in json.loads((BASE / "relationships.json").read_text())
    ]
    rng = random.Random(617)
    evidence = out / "evidence"
    evidence.mkdir(exist_ok=True)
    try:
        for trial in range(-1, a.repeats):
            rng.shuffle(tasks)
            for task in tasks:
                name = task.get("symbol", task.get("query"))
                args = {
                    "project": project,
                    "name_pattern": "^" + re.escape(name) + "$",
                    "limit": 1000,
                }
                start = time.perf_counter_ns()
                found = json.loads(text_result(c.call("search_graph", args)))
                if found.get("has_more"):
                    raise RuntimeError("Unexpected symbol truncation")
                matches = [
                    r
                    for r in found.get("results", [])
                    if r.get("file_path") == task["path"]
                ]
                raw = {"search_graph": found}
                if task["kind"] == "callers" and matches:
                    raw["trace_path"] = json.loads(
                        text_result(
                            c.call(
                                "trace_path",
                                {
                                    "project": project,
                                    "function_name": matches[0]["qualified_name"],
                                    "direction": "inbound",
                                    "depth": 1,
                                    "include_tests": True,
                                },
                            )
                        )
                    )
                ms = (time.perf_counter_ns() - start) / 1e6
                (evidence / (task["id"] + ".json")).write_text(
                    json.dumps(raw, indent=2)
                )
                result["trials"].append(
                    {
                        "id": task["id"],
                        "kind": task["kind"],
                        "trial": trial,
                        "milliseconds": ms,
                        "expected_file_found": bool(matches),
                        "output_bytes": len(json.dumps(raw).encode()),
                    }
                )
            (out / "query-results.json").write_text(json.dumps(result, indent=2))
            print("codebase query trial", trial, flush=True)
        schema = json.loads(
            text_result(c.call("get_graph_schema", {"project": project}))
        )
        (out / "schema.json").write_text(json.dumps(schema, indent=2))
    finally:
        c.close()


if __name__ == "__main__":
    main()
