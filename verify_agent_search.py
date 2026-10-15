"""Validate saved multi-turn trials against source-derived caller sets."""

import argparse
import ast
import json
from build_relationships import Calls
from agent_search_bench import BASE, CORPUS, OUT


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args()
    tasks = {r["id"]: r for r in json.loads((BASE / "relationships.json").read_text())}
    for task in tasks.values():
        tree = ast.parse((CORPUS / task["path"]).read_text())
        names = set()
        for node in tree.body:
            if (
                isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name != task["symbol"]
            ):
                visitor = Calls()
                for statement in node.body:
                    visitor.visit(statement)
                if task["symbol"] in visitor.names:
                    names.add(node.name)
        assert names == {c["name"] for c in task["expected_callers"]}
    rows = [json.loads(s) for s in OUT.read_text().splitlines()]
    errors = [r for r in rows if r["status"] == "api_error"]
    rows = [r for r in rows if r["status"] != "api_error"]
    assert len({(r["id"], r["arm"]) for r in rows}) == len(rows)
    expected_pairs = {(id, arm) for id in tasks for arm in ("fff", "rg", "choice")}
    actual_pairs = {(r["id"], r["arm"]) for r in rows}
    assert actual_pairs <= expected_pairs
    if not args.allow_partial:
        assert actual_pairs == expected_pairs
    calls_count = 0
    for row in rows:
        assert row["status"] != "api_error"
        assert (
            row["initial_messages"][1]["content"]
            == f"Repository: {tasks[row['id']]['path'].split('/')[0]}\nTarget function: {tasks[row['id']]['symbol']}"
        )
        allowed = {
            "fff": {"fff_search"},
            "rg": {"rg_search"},
            "choice": {"fff_search", "rg_search"},
        }[row["arm"]] | {"read", "answer"}
        answer = None
        for turn in row["trace"]:
            for call in turn.get("calls", []):
                calls_count += 1
                action = call.get("action", {})
                assert action.get("tool") in allowed
                if action["tool"] == "answer":
                    answer = action
        task = tasks[row["id"]]
        exact = bool(
            answer
            and answer.get("path") == task["path"]
            and isinstance(answer.get("callers"), list)
            and set(answer["callers"]) == {c["name"] for c in task["expected_callers"]}
        )
        assert exact == row["exact"]
    replay = json.loads((BASE / "agent-search-replay.json").read_text())
    assert replay["summary"]
    # Search discrepancies are experimental findings, not corrupt artifacts.
    result = {
        "trials": len(rows),
        "complete": actual_pairs == expected_pairs,
        "api_errors": len(errors),
        "pending_trials": len(expected_pairs - actual_pairs),
        "source_oracles": len(tasks),
        "recorded_tool_calls": calls_count,
        "paired_replay_queries": replay["unique_requests"],
        "passed": True,
    }
    (BASE / "agent-search-verification.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    print(json.dumps(result))


if __name__ == "__main__":
    main()
