#!/usr/bin/env python3
"""Sequential local rerun; API calls require the explicit --with-model flag."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--with-model",
        action="store_true",
        help="Resume model pilot using configured CLIProxy model",
    )
    p.add_argument(
        "--rerun-model",
        action="store_true",
        help="Archive existing model results and make fresh API requests",
    )
    p.add_argument(
        "--fresh-indexes",
        action="store_true",
        help="Archive this experiment's graph indexes before rebuilding",
    )
    a = p.parse_args()
    if a.rerun_model and not a.with_model:
        p.error("--rerun-model requires --with-model")
    python = BASE / "graphify/.venv/bin/python"
    if not python.exists():
        raise SystemExit("Run python3 bootstrap.py first")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    def archive(path):
        if path.exists():
            target = BASE / "history" / stamp / path.relative_to(BASE)
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)

    if a.fresh_indexes:
        archive(BASE / "codebase/full")
        archive(BASE / "graphify/run-hcl")
    if a.rerun_model:
        archive(BASE / "qa-results.jsonl")

    def run(script, *args, network=False):
        command = [str(python), str(BASE / script), *map(str, args)]
        if not network and script not in {
            "codebase_bench.py",
            "fff_mcp_bench.py",
            "fuzzy_bench.py",
            "targeted_evidence.py",
            "graphify/run.py",
        }:
            command = [
                "/usr/bin/sandbox-exec",
                "-p",
                "(version 1)(allow default)(deny network*)",
                *command,
            ]
        subprocess.run(command, cwd=BASE, check=True)

    if not (BASE / "graphify/run-hcl/index/graphify-out/graph.json").exists():
        run("graphify/run.py", "--output", BASE / "graphify/run-hcl")
    run("codebase_bench.py")
    run("graph_queries.py")
    run("text_bench.py")
    run("fff_mcp_bench.py", "--repeats", "3")
    run("fuzzy_bench.py")
    run("prepare_qa_evidence.py")
    run("targeted_evidence.py")
    if a.with_model:
        run("qa_pilot.py", network=True)
        run("qa_pilot.py", "--tools", "graphify-explain", "fff-usage", network=True)
    else:
        print("Model API calls disabled; existing model trials are retained.")
    if (BASE / "qa-results.jsonl").exists():
        run("summarize.py")
        run("verify.py")
    else:
        print(
            "Local tests complete. Run with --with-model to produce the model pilot and combined report."
        )


if __name__ == "__main__":
    main()
