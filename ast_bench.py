#!/usr/bin/env python3
"""Same-file structural call patterns in all scopes, not graph caller resolution.

Time process startup, capture, JSON parsing and byte-position extraction only.
Oracle preparation and correctness comparisons are outside the timing boundary.
"""

import argparse
import ast
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent


def oracle(source, symbol):
    starts = [0]
    for line in source.splitlines(keepends=True):
        starts.append(starts[-1] + len(line))
    return {
        (starts[node.lineno - 1] + node.col_offset,
         starts[node.end_lineno - 1] + node.end_col_offset)
        for node in ast.walk(ast.parse(source.decode("utf-8")))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == symbol
    }


def search(binary, path, symbol, timeout):
    proc = subprocess.run(
        [str(binary), "run", "--lang", "python", "--pattern",
         symbol + "($$$ARGS)", "--json=compact", str(path)],
        capture_output=True, timeout=timeout,
    )
    if proc.returncode not in (0, 1):
        raise ValueError("ast-grep failed")
    rows = json.loads(proc.stdout)
    if not isinstance(rows, list):
        raise ValueError("expected an ast-grep JSON array")
    positions = set()
    for row in rows:
        offsets = row["range"]["byteOffset"]
        start, end = offsets["start"], offsets["end"]
        if type(start) is not int or type(end) is not int or not 0 <= start < end:
            raise ValueError("invalid byte offsets")
        positions.add((start, end))
    return positions, len(proc.stdout)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeats", type=int, default=7)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--output", type=Path, default=BASE / "ast-results.json")
    args = parser.parse_args(argv)
    if args.repeats < 1 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error("repeats and timeout must be positive and finite")
    try:
        tasks = []
        corpus = (BASE / "corpus").resolve()
        for task in json.loads((BASE / "relationships.json").read_bytes()):
            path = (corpus / task["path"]).resolve()
            symbol = task["symbol"]
            if not path.is_relative_to(corpus) or not symbol.isidentifier():
                raise ValueError("invalid task")
            tasks.append((task["id"], path, symbol, oracle(path.read_bytes(), symbol)))
        results = {"tool": "ast-grep", "trials": []}
        rng = random.Random(617)
        binary = BASE / "tools/ast-grep/ast-grep"
        for trial in range(-1, args.repeats):
            rng.shuffle(tasks)
            for identifier, path, symbol, expected in tasks:
                start = time.perf_counter_ns()
                actual, output_bytes = search(binary, path, symbol, args.timeout)
                milliseconds = (time.perf_counter_ns() - start) / 1e6
                results["trials"].append({
                    "tool": "ast-grep", "query_id": identifier, "trial": trial,
                    "milliseconds": milliseconds, "exact": actual == expected,
                    "false_positive": len(actual - expected),
                    "false_negative": len(expected - actual),
                    "true_positive": len(actual & expected),
                    "expected_count": len(expected), "match_count": len(actual),
                    "output_bytes": output_bytes,
                })
        args.output.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError, AttributeError, SyntaxError,
            subprocess.TimeoutExpired):
        print("ast_bench: benchmark failed; check inputs and ast-grep", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
