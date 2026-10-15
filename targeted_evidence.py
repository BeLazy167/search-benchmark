#!/usr/bin/env python3
"""Caller-oriented configurations; target resolution never uses caller gold labels."""

import json
from pathlib import Path
import subprocess
import time
from fff_mcp_bench import make_client
from mcp_client import text_result

BASE = Path(__file__).resolve().parent
IDS = {
    "callers-00",
    "callers-01",
    "callers-02",
    "callers-04",
    "callers-05",
    "callers-06",
}


def main():
    graph = BASE / "graphify/run-hcl/index/graphify-out/graph.json"
    raw = json.loads(graph.read_text())
    tasks = [
        q
        for q in json.loads((BASE / "relationships.json").read_text())
        if q["id"] in IDS
    ]
    rows = []
    client = make_client()
    try:
        for q in tasks:
            out = BASE / "qa-evidence/fff-usage"
            out.mkdir(exist_ok=True, parents=True)
            start = time.perf_counter()
            text = text_result(
                client.call(
                    "grep",
                    {
                        "query": q["path"] + " " + q["symbol"],
                        "output_mode": "usage",
                        "context": 40,
                        "maxResults": 1000,
                    },
                )
            )
            rows.append(
                {
                    "id": q["id"],
                    "tool": "fff-usage",
                    "seconds": time.perf_counter() - start,
                }
            )
            (out / (q["id"] + ".txt")).write_text(text)
    finally:
        client.close()
    for q in tasks:
        out = BASE / "qa-evidence/graphify-explain"
        out.mkdir(exist_ok=True, parents=True)
        candidates = [
            n
            for n in raw["nodes"]
            if n.get("source_file") == q["path"]
            and n.get("label", "").removesuffix("()") == q["symbol"]
        ]
        if len(candidates) != 1:
            raise RuntimeError("Ambiguous target: " + q["id"])
        cmd = [
            "/usr/bin/sandbox-exec",
            "-p",
            "(version 1)(allow default)(deny network*)",
            str(BASE / "graphify/.venv/bin/python"),
            "-m",
            "graphify",
            "explain",
            candidates[0]["id"],
            "--graph",
            str(graph),
        ]
        start = time.perf_counter()
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            env={"PATH": "/usr/bin:/bin"},
            cwd=BASE / "graphify",
        )
        rows.append(
            {
                "id": q["id"],
                "tool": "graphify-explain-cli",
                "seconds": time.perf_counter() - start,
                "returncode": proc.returncode,
                "target_node_id": candidates[0]["id"],
                "command": cmd,
            }
        )
        if proc.returncode:
            raise RuntimeError(proc.stderr)
        (out / (q["id"] + ".txt")).write_text(proc.stdout)
    (BASE / "targeted-retrieval.json").write_text(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
