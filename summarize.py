#!/usr/bin/env python3
"""Build the report from saved observations, not hand-entered scores."""

import csv
import json
from pathlib import Path
import sqlite3
import statistics

BASE = Path(__file__).resolve().parent


def read(name):
    return json.loads((BASE / name).read_text())


def timing(rows):
    values = sorted(r["milliseconds"] for r in rows)
    return {
        "median_ms": statistics.median(values),
        "p95_ms": values[min(len(values) - 1, int(0.95 * len(values)))],
        "calls": len(values),
    }


def main():
    manifest = read("manifest.json")
    text = read("text-results.json")
    mcp = read("fff/mcp-results.json")
    cbm = read("codebase/full/query-results.json")
    graph = read("graphify/query-results.json")
    summary = {
        "corpus_sha256": manifest["corpus_sha256"],
        "files": len(manifest["files"]),
        "bytes": sum(f["bytes"] for f in manifest["files"]),
        "text": {},
        "graphs": {},
        "qa": {},
    }
    fuzzy = read("fff/fuzzy-results.json")
    summary["fff_filename_typos"] = {
        "hit_at_10": sum(row["hit_at_10"] for row in fuzzy),
        "cases": len(fuzzy),
    }
    for tool in ["ripgrep", "grep", "fff-sdk"]:
        rows = [r for r in text["trials"] if r["tool"] == tool and r["trial"] >= 0]
        summary["text"][tool] = {
            **timing(rows),
            "exact_trials": sum(r["exact"] for r in rows),
            "exact_queries": sum(r["exact"] for r in rows if r["trial"] == 0),
        }
    rows = [r for r in mcp["trials"] if r["trial"] >= 0]
    summary["text"]["fff-mcp"] = {
        **timing(rows),
        "exact_trials": sum(r["exact"] for r in rows),
        "exact_queries": sum(r["exact"] for r in rows if r["trial"] == 0),
    }
    cbm_edges = []
    for q in read("relationships.json"):
        raw = read("codebase/full/evidence/" + q["id"] + ".json")
        target = next(
            (
                n
                for n in raw["search_graph"].get("results", [])
                if n.get("file_path") == q["path"]
            ),
            None,
        )
        prefix = target["qualified_name"].rsplit(".", 1)[0] if target else None
        actual = {
            n["name"]
            for n in raw.get("trace_path", {}).get("callers", [])
            if n.get("qualified_name", "").rsplit(".", 1)[0] == prefix
        }
        expected = {n["name"] for n in q["expected_callers"]}
        cbm_edges.append(
            {
                "id": q["id"],
                "actual": sorted(actual),
                "expected": sorted(expected),
                "exact": actual == expected,
            }
        )
    for name, data in [("codebase-memory", cbm), ("graphify-query", graph)]:
        rows = [r for r in data["trials"] if r["trial"] >= 0]
        summary["graphs"][name] = {
            "symbol_query": timing([r for r in rows if r["kind"] == "symbol"]),
            "caller_query": timing([r for r in rows if r["kind"] == "callers"]),
        }
    summary["graphs"]["codebase-memory"]["initial_index_seconds"] = cbm["index"][
        "seconds"
    ]
    summary["graphs"]["codebase-memory"]["caller_exact"] = sum(
        r["exact"] for r in cbm_edges
    )
    summary["graphs"]["codebase-memory"]["caller_details"] = cbm_edges
    summary["graphs"]["graphify-query"]["initial_index_seconds"] = read(
        "graphify/run-hcl/results.json"
    )["runs"][0]["seconds"]
    summary["graphs"]["graphify-query"]["unchanged_index_seconds"] = read(
        "graphify/run-hcl/results.json"
    )["runs"][1]["seconds"]
    summary["graphs"]["graphify-query"]["caller_exact"] = sum(
        r["exact"] for r in graph["relationship_edges"]
    )
    qa = [
        json.loads(line)
        for line in (BASE / "qa-results.jsonl").read_text().splitlines()
    ]
    for tool in sorted({r["tool"] for r in qa}):
        rows = [r for r in qa if r["tool"] == tool]
        summary["qa"][tool] = {
            "exact": sum(r.get("exact_set_match", False) for r in rows),
            "trials": len(rows),
            "prompt_tokens": sum(
                r.get("usage", {}).get("prompt_tokens", 0) for r in rows
            ),
            "completion_tokens": sum(
                r.get("usage", {}).get("completion_tokens", 0) for r in rows
            ),
            "cached_prompt_tokens": sum(
                r.get("usage", {})
                .get("prompt_tokens_details", {})
                .get("cached_tokens", 0)
                for r in rows
            ),
            "reasoning_tokens": sum(
                r.get("usage", {})
                .get("completion_tokens_details", {})
                .get("reasoning_tokens", 0)
                for r in rows
            ),
            "median_evidence_bytes": statistics.median(
                r["prompt_evidence_bytes"] for r in rows
            ),
            "truncated_trials": sum(r["evidence_truncated"] for r in rows),
        }
    graph_raw = read("graphify/run-hcl/index/graphify-out/graph.json")
    graph_files = {n["source_file"] for n in graph_raw["nodes"] if n.get("source_file")}
    project = read("codebase/full/index.stdout.txt")["project"]
    db = BASE / "codebase/full/cache" / (project + ".db")
    with sqlite3.connect(db.as_uri() + "?mode=ro", uri=True) as conn:
        cbm_files = {
            r[0]
            for r in conn.execute(
                "select distinct file_path from nodes where label='File'"
            )
        }
    summary["repositories"] = []
    for repo in manifest["repositories"]:
        name = repo["name"]
        files = [f for f in manifest["files"] if f["path"].startswith(name + "/")]
        summary["repositories"].append(
            {
                "repo": name,
                "commit": repo["commit"],
                "corpus_files": len(files),
                "bytes": sum(f["bytes"] for f in files),
                "codebase_file_nodes": sum(f["path"] in cbm_files for f in files),
                "graphify_source_files": sum(f["path"] in graph_files for f in files),
            }
        )
    (BASE / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    with (BASE / "repository-coverage.csv").open("w") as out:
        writer = csv.DictWriter(out, fieldnames=list(summary["repositories"][0]))
        writer.writeheader()
        writer.writerows(summary["repositories"])
    lines = [
        "# qBraid search-tool benchmark",
        "",
        "Recommendation: keep codebase-memory-mcp for relationships and ripgrep for exhaustive text checks. fff is worth an optional trial for repeated discovery. This experiment does not establish a need to add Graphify alongside the existing codebase graph.",
        "",
        f"Corpus: {summary['files']:,} files, {summary['bytes']:,} bytes, 29 committed top-level repositories. `qbraid-review-harness` has no HEAD and is excluded. Exact commits, file hashes, exclusions, and per-repo coverage are saved in `manifest.json` and `repository-coverage.csv`.",
        "",
        "## Exact text retrieval",
        "",
        "31 case-sensitive fixed-string queries: one deterministic anchor from each eligible repo plus broad and absent terms. The independent oracle counts matching path/line pairs. The table excludes warm-up. No OS caches were purged.",
        "",
        "| Tool/interface | Median ms | P95 ms | Exact query sets | Repetitions |",
        "|---|---:|---:|---:|---:|",
    ]
    for tool, r in summary["text"].items():
        lines.append(
            f"| {tool} | {r['median_ms']:.1f} | {r['p95_ms']:.1f} | {r['exact_queries']}/31 | {r['calls'] // 31} |"
        )
    lines += [
        "",
        f"fff SDK directory-scan/startup measurement: {text['fff_initial_scan_seconds']:.3f}s. The first full workload pass is warm-up and may absorb remaining content-index work. This is not comparable to a completed structural graph build.",
        "",
        "SDK calls retain the index in-process. CLI results include process startup, capture, and normalization. fff MCP uses persistent stdio, requests up to one million results, and follows every returned cursor. It still caps matches per file and uses smart-case/fuzzy behavior. Its faster incomplete output is not an exact-search speed win. The SDK was explicitly configured for case-sensitive plain search and complete pagination.",
        "",
        f"fff filename typo smoke test: {summary['fff_filename_typos']['hit_at_10']}/{summary['fff_filename_typos']['cases']} target files appeared in the first 10 results. These are six constructed typos, not a broad relevance benchmark. Git-history ranking is not evaluated because the archive corpus has no Git metadata.",
        "",
        "## Structural indexing and retrieval",
        "",
        "| Tool | Initial graph build | Correct direct caller sets |",
        "|---|---:|---:|",
        f"| codebase-memory-mcp 0.8.1, full, LSP disabled | {cbm['index']['seconds']:.2f}s | {summary['graphs']['codebase-memory']['caller_exact']}/12 |",
        f"| Graphify 0.9.56, code-only, no clustering, HCL parser installed | {summary['graphs']['graphify-query']['initial_index_seconds']:.2f}s | {summary['graphs']['graphify-query']['caller_exact']}/12 |",
        "",
        f"Graphify unchanged cached extraction: {summary['graphs']['graphify-query']['unchanged_index_seconds']:.2f}s. The initial default installation skipped 290 Terraform files; the reported build uses its optional HCL parser. Four syntax-error warnings remain in existing TSX input; these are parser reports, not diagnosed application defects.",
        "",
        "Caller truth comes from Python AST parsing of direct calls between top-level functions in the same file, with nested scopes excluded. It is a small, deliberately checkable suite across six repos. No claim is made about dynamic dispatch, cross-file alias resolution, language-server quality, or cross-repo HTTP contracts.",
        "",
        "| Warm query interface | Symbol median ms | Caller median ms |",
        "|---|---:|---:|",
    ]
    for tool, r in summary["graphs"].items():
        lines.append(
            f"| {tool} | {r['symbol_query']['median_ms']:.2f} | {r['caller_query']['median_ms']:.2f} |"
        )
    lines += [
        "",
        "Codebase timings include persistent MCP and JSON handling; caller work includes symbol resolution plus trace_path. Graphify timings call its pinned MCP query function in-process, with graph load excluded, depth 2, and requested token budget 2,000. These are different query operations. Graphify exact-node `explain` is evaluated separately below, including resolving the target by its supplied symbol/file.",
        "",
        "## Fixed-evidence model pilot",
        "",
        "Model: `gpt-5.3-codex-spark` through the user-selected CLIProxy, low reasoning effort requested. Six same-file caller questions, two repetitions, identical prompts, randomized order. The model sees no tool name or gold answer. Evidence is capped at 12,000 UTF-8 bytes for every tool. Responses are graded by exact caller-name sets, not an LLM judge.",
        "",
        "| Evidence configuration | Exact answers | Input tokens | Output tokens incl. reasoning |",
        "|---|---:|---:|---:|",
    ]
    for tool, r in summary["qa"].items():
        lines.append(
            f"| {tool} | {r['exact']}/{r['trials']} | {r['prompt_tokens']:,} | {r['completion_tokens']:,} |"
        )
    lines += [
        "",
        "The targeted Graphify result matters: its graph contains the answers, while broad natural-language query scoring can bury them. The exact-node explain configuration matches codebase on this pilot. fff content and usage output both miss caller evidence in this fixed bundle; a real agent could recover by reading the file. Grep and ripgrep use 40 preceding and 5 following context lines on the supplied file. This pilot has no follow-up read, autonomous tool choice, or code changes, so it is not a productivity leaderboard.",
        "",
        "The targeted Graphify and fff usage checks were added after observing the broad-query results. They are disclosed as follow-up configurations, not a preregistered competition. Graphify resolves only the target symbol/file, never the expected callers. Raw requests, answers, token breakdowns, and grading are in `qa-results.jsonl`. Luna quota failures and the unavailable plain gpt-5.3-codex alias are also recorded; no successful Luna run is claimed.",
        "",
        "## Reproduction and limits",
        "",
        "See `README.md` for commands, `RESEARCH.md` for primary-source benchmark inspiration, and `verify.py` for integrity and correctness checks. Timings will vary with machine load. Pinned corpus hashes and correctness outcomes should reproduce on this configuration. SDK/native binaries are pinned for macOS arm64; the installed codebase binary SHA256 is recorded rather than silently replaced.",
        "",
        "The first text run and the first codebase full index included a Graphify-generated cache file. They are retained under names containing `invalid-extra-cache` and excluded from the reported results. The final text run and codebase index use the verified clean corpus. Graphify excludes its own output directory; its graph was checked to contain no sidecar source nodes. The rerun configuration explicitly routes Graphify output outside the corpus.",
        "",
        "All local parsing/search runs deny network. No application server, database mutation, primary-checkout edit, push, or publishing was performed. The corpus excludes dirty/untracked files, hidden paths, symlinks, submodule contents, listed generated/dependency directories, common lockfiles and credential/environment filenames, binary/non-UTF8 data, and files larger than 1 MiB. Coverage therefore means this documented text corpus, not every byte on disk.",
        "",
    ]
    (BASE / "REPORT.md").write_text("\n".join(lines))
    print(json.dumps({"text": summary["text"], "qa": summary["qa"]}, indent=2))


if __name__ == "__main__":
    main()
