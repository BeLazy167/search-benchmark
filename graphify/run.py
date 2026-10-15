#!/usr/bin/env python3
"""Reproduce Graphify AST-only indexing and command queries. No network during runs."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import time

HERE = Path(__file__).resolve().parent
COMMIT = "67f99bd0059dd1bac9e44382907ef9f10098b39f"


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--python", default=str(HERE / ".venv/bin/python"))
    p.add_argument("--corpus", type=Path, default=HERE.parent / "corpus")
    p.add_argument("--output", type=Path, default=HERE / "run")
    p.add_argument("--queries", type=Path)
    p.add_argument("--skip-index", action="store_true")
    p.add_argument("--repeats", type=int, default=5)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    home = out / "isolated-home"
    home.mkdir(exist_ok=True)
    env = {
        "XDG_CACHE_HOME": str(home / "cache"),
        "XDG_CONFIG_HOME": str(home / "config"),
        "PATH": "/usr/bin:/bin",
        "LANG": "en_US.UTF-8",
        "GRAPHIFY_OUT": str(out / "index" / "graphify-out"),
        "PYTHONHASHSEED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
    }
    sandbox = shutil.which("sandbox-exec")
    prefix = (
        [sandbox, "-p", "(version 1) (allow default) (deny network*)"]
        if sandbox
        else []
    )
    if not sandbox:
        raise SystemExit(
            "This macOS run requires sandbox-exec to deny network. Adapt to an equivalent OS network sandbox first."
        )
    base = prefix + [str(Path(a.python).absolute()), "-m", "graphify"]
    result_file = out / "results.json"
    results = (
        json.loads(result_file.read_text())
        if a.skip_index and result_file.exists()
        else {
            "tool": "graphify",
            "version": "0.9.56",
            "commit": COMMIT,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "corpus": str(a.corpus.resolve()),
            "network_denied": True,
            "mode": "local AST only; no clustering, no semantic LLM pass",
            "runs": [],
        }
    )
    manifest = a.corpus.parent / "manifest.json"
    if manifest.exists():
        results["manifest_sha256"] = hashlib.sha256(manifest.read_bytes()).hexdigest()

    def run(name, args):
        start = time.perf_counter()
        proc = subprocess.run(
            base + args, cwd=out, env=env, capture_output=True, text=True
        )
        elapsed = time.perf_counter() - start
        (out / (name + ".stdout.txt")).write_text(proc.stdout)
        (out / (name + ".stderr.txt")).write_text(proc.stderr)
        row = {
            "name": name,
            "seconds": elapsed,
            "returncode": proc.returncode,
            "command": base + args,
            "stdout_bytes": len(proc.stdout.encode()),
            "stderr_bytes": len(proc.stderr.encode()),
        }
        results["runs"].append(row)
        result_file.write_text(json.dumps(results, indent=2) + "\n")
        if proc.returncode:
            raise RuntimeError(f"{name} failed; see {out / (name + '.stderr.txt')}")
        return row

    graph_dir = out / "index"
    graph = graph_dir / "graphify-out" / "graph.json"
    if not a.skip_index:
        if graph_dir.exists():
            raise SystemExit(
                "Use a fresh --output directory for initial indexing, or --skip-index to query the existing graph."
            )
        args = [
            "extract",
            str(a.corpus.resolve()),
            "--code-only",
            "--no-cluster",
            "--timing",
            "--out",
            str(graph_dir),
            "--max-workers",
            "4",
        ]
        run("initial-index", args)
        raw = json.loads(graph.read_text())
        nodes = raw.get("nodes", [])
        edges = raw.get("edges", raw.get("links", []))
        from collections import Counter

        results["index"] = {
            "nodes": len(nodes),
            "edges": len(edges),
            "graph_bytes": graph.stat().st_size,
            "total_output_bytes": sum(
                f.stat().st_size for f in graph_dir.rglob("*") if f.is_file()
            ),
            "source_files": len(
                {n.get("source_file") for n in nodes if n.get("source_file")}
            ),
            "relations": dict(Counter(e.get("relation", "") for e in edges)),
            "confidence_tags": dict(Counter(e.get("confidence", "") for e in edges)),
        }
        run("unchanged-index", args)
    if a.queries:
        queries = json.loads(a.queries.read_text())
        if isinstance(queries, dict):
            queries = queries["queries"]
        results["queries"] = []
        for query in queries:
            command = query.get(
                "graphify_command",
                ["explain", query.get("symbol", query.get("pattern", ""))],
            )
            elapsed = []
            for i in range(a.repeats + 1):
                row = run(f"{query['id']}-{i}", command + ["--graph", str(graph)])
                if i:
                    elapsed.append(row["seconds"])
            results["queries"].append(
                {
                    "id": query["id"],
                    "command": command,
                    "warmup_runs": 1,
                    "seconds": elapsed,
                    "median_seconds": statistics.median(elapsed),
                }
            )
    result_file.write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results.get("index", {}), indent=2))


if __name__ == "__main__":
    main()
