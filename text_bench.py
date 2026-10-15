#!/usr/bin/env python3
"""Exact case-sensitive line matches, fixed committed corpus, independent oracle."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import statistics
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--repeats", type=int, default=7)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--ugrep", type=Path, help="Optional ugrep executable")
    p.add_argument("--gnu-grep", type=Path, help="Optional GNU grep executable")
    p.add_argument("--output", type=Path, default=BASE / "text-results.json")
    a = p.parse_args()
    if a.repeats < 1:
        p.error("--repeats must be positive")
    corpus = BASE / "corpus"
    manifest = json.loads((BASE / "manifest.json").read_text())
    for f in manifest["files"]:
        if hashlib.sha256((corpus / f["path"]).read_bytes()).hexdigest() != f["sha256"]:
            raise RuntimeError("Corpus changed: " + f["path"])
    expected_paths = {f["path"] for f in manifest["files"]}
    actual_paths = {
        f.relative_to(corpus).as_posix() for f in corpus.rglob("*") if f.is_file()
    }
    if actual_paths != expected_paths:
        raise RuntimeError(
            "Unexpected or missing corpus files: "
            + str(sorted(actual_paths ^ expected_paths)[:10])
        )
    queries = json.loads((BASE / "queries.json").read_text())
    if a.smoke:
        queries = queries[:2]
    sys.path.insert(0, str(BASE / "fff/sdk"))
    import fff

    cache = BASE / "fff/cache"
    cache.mkdir(exist_ok=True)
    start = time.perf_counter()
    finder = fff.FileFinder(
        str(corpus),
        watch=False,
        frecency_db_path=str(cache / "frecency"),
        history_db_path=str(cache / "history"),
    )
    if not finder.wait_for_scan_blocking(60000):
        raise RuntimeError("fff initial scan timed out")
    index_seconds = time.perf_counter() - start
    commands = {
        "ripgrep": [
            (
                shutil.which("rg")
                or json.loads((BASE / "tools.json").read_text())["ripgrep"]["path"]
            ),
            "--no-config",
            "--hidden",
            "--no-ignore",
            "-F",
            "-n",
            "--no-heading",
            "--color",
            "never",
        ],
        "grep": ["/usr/bin/grep", "-r", "-F", "-n", "-H"],
    }
    if a.ugrep:
        commands["ugrep"] = [str(a.ugrep.resolve()), "--no-config", "--color=never", "-r", "-F", "-n", "-H"]
    if a.gnu_grep:
        commands["gnu-grep"] = [str(a.gnu_grep.resolve()), "--color=never", "-r", "-F", "-n", "-H"]
    tool_names = [*commands, "fff-sdk"]
    if not commands["ripgrep"][0]:
        raise RuntimeError("rg missing from PATH")
    env = {"PATH": "/usr/bin:/bin", "LC_ALL": "C"}

    def search(tool, query):
        if tool == "fff-sdk":
            matches, cursor, pages, output_bytes = set(), None, 0, 0
            while True:
                r = finder.grep(
                    query,
                    mode="plain",
                    smart_case=False,
                    max_file_size=1048576,
                    max_matches_per_file=1000000,
                    page_limit=10000,
                    time_budget_ms=0,
                    cursor=cursor,
                )
                if r.regex_fallback_error:
                    raise RuntimeError(r.regex_fallback_error)
                prior = len(matches)
                for m in r.items:
                    matches.add((m.relative_path.removeprefix("./"), m.line_number))
                    output_bytes += len(
                        f"{m.relative_path}:{m.line_number}:{m.line_content}\n".encode()
                    )
                pages += 1
                if not r.has_more:
                    return matches, output_bytes, pages
                if r.next_cursor() is None or pages > 10000 or len(matches) == prior:
                    raise RuntimeError("fff pagination made no progress")
                cursor = r.next_cursor()
        proc = subprocess.run(
            commands[tool] + ["--", query, "."],
            cwd=corpus,
            env=env,
            capture_output=True,
        )
        if proc.returncode not in (0, 1):
            raise RuntimeError(
                f"{tool} exited {proc.returncode}: {proc.stderr[:500]!r}"
            )
        matches = set()
        for line in proc.stdout.split(b"\n"):
            if not line:
                continue
            path, number, _ = line.split(b":", 2)
            matches.add((path.decode().removeprefix("./"), int(number)))
        return matches, len(proc.stdout), 1

    results = {
        "corpus_sha256": manifest["corpus_sha256"],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
        "fff_version": fff.__version__,
        "fff_initial_scan_seconds": index_seconds,
        "timing_boundary": "CLI process+capture+parse; SDK call+normalize; correctness comparison excluded; warm OS cache, no disk-cache purge",
        "commands": commands,
        "versions": {},
        "trials": [],
    }
    for tool, command in commands.items():
        proc = subprocess.run(
            [command[0], "--version"], env=env, capture_output=True, text=True
        )
        results["versions"][tool] = (proc.stdout + proc.stderr).splitlines()[0]
        results["versions"][tool + "_sha256"] = hashlib.sha256(
            Path(command[0]).read_bytes()
        ).hexdigest()
    tasks = [(tool, q) for tool in tool_names for q in queries]
    rng = random.Random(617)
    try:
        for trial in range(-1, a.repeats):
            rng.shuffle(tasks)
            for tool, q in tasks:
                start = time.perf_counter_ns()
                actual, output_bytes, pages = search(tool, q["query"])
                ms = (time.perf_counter_ns() - start) / 1e6
                expected = {(x["path"], x["line"]) for x in q["expected"]}
                fp, fn = actual - expected, expected - actual
                results["trials"].append(
                    {
                        "tool": tool,
                        "query_id": q["id"],
                        "trial": trial,
                        "milliseconds": ms,
                        "match_count": len(actual),
                        "expected_count": len(expected),
                        "true_positive": len(actual & expected),
                        "false_positive": len(fp),
                        "false_negative": len(fn),
                        "exact": actual == expected,
                        "output_bytes": output_bytes,
                        "pages": pages,
                        "extra_examples": sorted(fp)[:5],
                        "missing_examples": sorted(fn)[:5],
                    }
                )
            a.output.write_text(json.dumps(results, indent=2) + "\n")
            print("completed trial", trial, flush=True)
    finally:
        finder.close()
    for tool in tool_names:
        rows = [r for r in results["trials"] if r["tool"] == tool and r["trial"] >= 0]
        print(
            tool,
            "median_ms",
            round(statistics.median(r["milliseconds"] for r in rows), 3),
            "exact",
            sum(r["exact"] for r in rows),
            "/",
            len(rows),
        )


if __name__ == "__main__":
    main()
