#!/usr/bin/env python3
"""Fail on corpus contamination, incorrect exact search, or incomplete saved trials."""

from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3

BASE = Path(__file__).resolve().parent


def read(name):
    return json.loads((BASE / name).read_text())


def main():
    manifest = read("manifest.json")
    corpus = BASE / "corpus"
    expected = {f["path"]: f for f in manifest["files"]}
    actual = {
        p.relative_to(corpus).as_posix() for p in corpus.rglob("*") if p.is_file()
    }
    assert actual == set(expected), "Unexpected or missing corpus files"
    for path, entry in expected.items():
        assert (
            hashlib.sha256((corpus / path).read_bytes()).hexdigest() == entry["sha256"]
        ), path
    assert (
        hashlib.sha256(
            json.dumps(manifest["files"], sort_keys=True).encode()
        ).hexdigest()
        == manifest["corpus_sha256"]
    )
    queries = read("queries.json")
    query_ids = {q["id"] for q in queries}
    for q in queries:
        assert q["query"] and "\n" not in q["query"] and q["query"].isascii()
        oracle = set()
        for path in expected:
            data = (corpus / path).read_bytes()
            if q["query"].encode() in data:
                oracle.update(
                    (path, i)
                    for i, line in enumerate(data.split(b"\n"), 1)
                    if q["query"].encode() in line
                )
        assert oracle == {(m["path"], m["line"]) for m in q["expected"]}, q["id"]
    text = read("text-results.json")
    assert text["corpus_sha256"] == manifest["corpus_sha256"]
    for tool in ["ripgrep", "grep", "fff-sdk"]:
        rows = [r for r in text["trials"] if r["tool"] == tool and r["trial"] >= 0]
        assert len(rows) == len(query_ids) * 7, (tool, len(rows))
        assert len({(r["query_id"], r["trial"]) for r in rows}) == len(rows)
        assert all(
            r["exact"] and r["false_positive"] == 0 and r["false_negative"] == 0
            for r in rows
        ), tool
    mcp = read("fff/mcp-results.json")
    rows = [r for r in mcp["trials"] if r["trial"] >= 0]
    assert len(rows) == len(query_ids) * 3
    for qid in query_ids:
        signatures = {
            (r["true_positive"], r["false_positive"], r["false_negative"])
            for r in rows
            if r["query_id"] == qid
        }
        assert len(signatures) == 1, ("fff MCP result drift", qid)
    summary = read("summary.json")
    assert summary["fff_filename_typos"] == {"hit_at_10": 6, "cases": 6}
    assert summary["graphs"]["codebase-memory"]["caller_exact"] == 12
    assert summary["graphs"]["graphify-query"]["caller_exact"] == 12
    project = read("codebase/full/index.stdout.txt")["project"]
    db = BASE / "codebase/full/cache" / (project + ".db")
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        assert (
            conn.execute(
                "select count(*) from nodes where file_path like 'graphify-out/%'"
            ).fetchone()[0]
            == 0
        )
    # Verify target/caller facts; auxiliary degree metadata and row order can vary on rebuild.
    for task in read("relationships.json"):
        frozen = json.loads(
            (BASE / "qa-evidence/codebase" / (task["id"] + ".txt")).read_text()
        )
        fresh = read("codebase/full/evidence/" + task["id"] + ".json")

        def facts(raw):
            nodes = {
                (n["qualified_name"], n["file_path"])
                for n in raw["search_graph"].get("results", [])
            }
            callers = {
                n["qualified_name"]
                for n in raw.get("trace_path", {}).get("callers", [])
            }
            return nodes, callers

        assert facts(frozen) == facts(fresh), (
            "Codebase evidence facts changed",
            task["id"],
        )
    rows = [
        json.loads(line)
        for line in (BASE / "qa-results.jsonl").read_text().splitlines()
    ]
    expected_tools = {
        "codebase",
        "graphify",
        "graphify-explain",
        "fff-mcp",
        "fff-usage",
        "ripgrep",
        "grep",
    }
    assert Counter(r["tool"] for r in rows) == Counter({t: 12 for t in expected_tools})
    assert len({(r["tool"], r["task_id"], r["repeat"]) for r in rows}) == 84
    assert all(
        r["status"] == "ok" and r["model"] == "gpt-5.3-codex-spark" for r in rows
    )
    for r in rows:
        assert r["exact_set_match"] == (set(r["callers"]) == set(r["expected_callers"]))
    print(
        f"PASS: {len(actual):,} file hashes, {len(queries)} independent query oracles, 651 exact-search trials, 93 MCP trials, 24 caller sets, 84 model trials."
    )


if __name__ == "__main__":
    main()
