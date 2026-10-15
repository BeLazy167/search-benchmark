#!/usr/bin/env python3
"""Graphify's pinned MCP query implementation, loaded once as a Python library."""

import argparse
import json
from pathlib import Path
import random
import statistics
import time

BASE = Path(__file__).resolve().parent


def main():
    p = argparse.ArgumentParser()
    p.add_argument(
        "--graph",
        type=Path,
        default=BASE / "graphify/run-hcl/index/graphify-out/graph.json",
    )
    p.add_argument("--repeats", type=int, default=7)
    a = p.parse_args()
    from graphify.serve import _load_graph, _query_graph_text

    started = time.perf_counter()
    graph = _load_graph(str(a.graph))
    load_seconds = time.perf_counter() - started
    symbols = json.loads((BASE / "symbols.json").read_text())
    relationships = json.loads((BASE / "relationships.json").read_text())
    tasks = [
        {
            "id": f"symbol-{i:02d}",
            "question": q["query"],
            "path": q["path"],
            "symbol": q["query"],
            "kind": "symbol",
        }
        for i, q in enumerate(symbols)
    ]
    tasks += [
        {
            "id": q["id"],
            "question": f"What calls {q['symbol']}?",
            **q,
            "kind": "callers",
        }
        for q in relationships
    ]
    result = {
        "tool": "graphify",
        "interface": "pinned graphify.serve._query_graph_text used by MCP; transport excluded",
        "graph_load_seconds": load_seconds,
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "trials": [],
    }
    output = BASE / "graphify/query-results.json"
    evidence = BASE / "graphify/evidence"
    evidence.mkdir(exist_ok=True)
    rng = random.Random(617)
    for trial in range(-1, a.repeats):
        rng.shuffle(tasks)
        for task in tasks:
            start = time.perf_counter_ns()
            text = _query_graph_text(
                graph,
                task["question"],
                depth=2,
                token_budget=2000,
                graph_path=str(a.graph),
            )
            ms = (time.perf_counter_ns() - start) / 1e6
            (evidence / (task["id"] + ".txt")).write_text(text)
            row = {
                "id": task["id"],
                "kind": task["kind"],
                "trial": trial,
                "milliseconds": ms,
                "output_bytes": len(text.encode()),
                "expected_file_in_output": task["path"] in text,
                "symbol_in_output": task["symbol"] in text,
            }
            if task["kind"] == "callers":
                row["expected_caller_names_in_output"] = [
                    q["name"] for q in task["expected_callers"] if q["name"] in text
                ]
                row["expected_caller_count"] = len(task["expected_callers"])
            result["trials"].append(row)
        output.write_text(json.dumps(result, indent=2) + "\n")
        print("graphify query trial", trial, flush=True)
    # Graph coverage is distinct from ranked query evidence. Verify directed arcs from stored source/target.
    raw = json.loads(a.graph.read_text())
    nodes = {n["id"]: n for n in raw["nodes"]}
    result["relationship_edges"] = []
    for q in relationships:
        targets = {
            nid
            for nid, n in nodes.items()
            if n.get("source_file") == q["path"]
            and n.get("label", "").removesuffix("()") == q["symbol"]
        }
        callers = set()
        for edge in raw.get("links", raw.get("edges", [])):
            if edge.get("relation", "").lower() != "calls":
                continue
            src, tgt = (
                edge.get("_src", edge["source"]),
                edge.get("_tgt", edge["target"]),
            )
            if tgt in targets and nodes.get(src, {}).get("source_file") == q["path"]:
                callers.add(nodes[src].get("label", "").removesuffix("()"))
        expected = {c["name"] for c in q["expected_callers"]}
        result["relationship_edges"].append(
            {
                "id": q["id"],
                "target_found": bool(targets),
                "expected": sorted(expected),
                "actual": sorted(callers),
                "exact": callers == expected,
            }
        )
    output.write_text(json.dumps(result, indent=2) + "\n")
    print(
        "median query ms",
        statistics.median(
            r["milliseconds"] for r in result["trials"] if r["trial"] >= 0
        ),
    )


if __name__ == "__main__":
    main()
