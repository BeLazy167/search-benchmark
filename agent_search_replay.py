"""Replay agents' actual queries against both backends, with paired equality checks."""

import json
import random
import statistics
from agent_search_bench import BASE, OUT, Client


def main():
    requests = {}
    for row in map(json.loads, OUT.read_text().splitlines()):
        for turn in row["trace"]:
            for call in turn.get("calls", []):
                action = call.get("action", {})
                if action.get("tool") in ("fff_search", "rg_search"):
                    query = {k: v for k, v in action.items() if k != "tool"}
                    requests[json.dumps(query, sort_keys=True)] = query
    client = Client()
    rows = []
    mismatches = []
    rng = random.Random(923)
    try:
        for repetition in range(-1, 3):
            queries = list(requests.values())
            rng.shuffle(queries)
            for query in queries:
                tools = ["fff_search", "rg_search"]
                rng.shuffle(tools)
                results = {}
                for tool in tools:
                    response = client.act(dict(query, tool=tool))
                    if "error" in response["result"]:
                        raise RuntimeError(response["result"])
                    results[tool] = response["result"]
                    rows.append(
                        {
                            "repetition": repetition,
                            "tool": tool,
                            "query": query,
                            "seconds": response["seconds"],
                        }
                    )
                if results["fff_search"] != results["rg_search"]:
                    mismatches.append(
                        {
                            "repetition": repetition,
                            "query": query,
                            "fff_total": results["fff_search"]["total"],
                            "rg_total": results["rg_search"]["total"],
                        }
                    )
        summary = {
            tool: {
                "median_ms": statistics.median(
                    r["seconds"]
                    for r in rows
                    if r["tool"] == tool and r["repetition"] >= 0
                )
                * 1000,
                "measured_calls": sum(
                    r["tool"] == tool and r["repetition"] >= 0 for r in rows
                ),
            }
            for tool in ("fff_search", "rg_search")
        }
        output = {
            "unique_requests": len(requests),
            "all_outputs_equal": not mismatches,
            "mismatches": mismatches,
            "startup_seconds": client.startup,
            "summary": summary,
            "trials": rows,
        }
        (BASE / "agent-search-replay.json").write_text(
            json.dumps(output, indent=2) + "\n"
        )
        print(json.dumps({k: v for k, v in output.items() if k != "trials"}, indent=2))
    finally:
        client.close()


if __name__ == "__main__":
    main()
