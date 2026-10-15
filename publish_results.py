#!/usr/bin/env python3
"""Export only allowlisted tools and numeric aggregates from a private run.

Schema 1 has corpus {file_count, byte_count, repo_count}, text keyed by tool,
and optional graphs and ast_patterns keyed by tool. Text metrics are median_ms, p95_ms,
measured_trial_count, query_count, exact_query_count, false_positive, and
false_negative. Trial -1 is warm-up. P95 uses nearest rank, ceil(0.95 * n).
An exact query requires every measured repetition to be exact.
AST patterns use these metrics for byte spans of named calls across all scopes.

Graphs have optional symbol_query/caller_query timing metrics, index seconds,
and same_file_callers. Symbol success uses all measured repetitions. Caller
exactness compares the final saved evidence snapshot with relationships.json's
AST oracle; it does not establish exactness across repetitions. Unsupported
metrics are omitted with a fixed diagnostic on stderr. No corpus is opened.
"""

import argparse
import json
import math
import os
from pathlib import Path
import sys
import tempfile


TEXT_TOOLS = frozenset({"ripgrep", "grep", "fff-sdk", "ugrep", "gnu-grep"})
TOOL_ALLOWLIST = TEXT_TOOLS | {"fff-mcp", "codebase-memory-mcp", "graphify", "ast-grep"}
MISSING = object()
COUNT_FIELDS = (
    "match_count", "actual_count", "expected_count", "true_positive",
    "false_positive", "false_negative", "output_bytes", "pages",
    "expected_caller_count",
)
INPUT_FILES = (
    "manifest.json", "text-results.json", "ast-results.json", "fff/mcp-results.json",
    "codebase/full/query-results.json", "relationships.json",
    "graphify/run-hcl/results.json", "graphify/query-results.json",
)


class InvalidResults(ValueError):
    """A fixed, public-safe error message, never raw input or exception text."""


def _object(value):
    if not isinstance(value, dict):
        raise InvalidResults("expected a JSON object")
    return value


def _array(value):
    if not isinstance(value, list):
        raise InvalidResults("expected a JSON array")
    return value


def _identifier(value):
    if not isinstance(value, str) or not value:
        raise InvalidResults("expected a nonempty identifier")
    return value


def _count(value):
    if type(value) is not int or value < 0:
        raise InvalidResults("counts must be nonnegative integers")
    return value


def _number(value):
    if type(value) not in (int, float) or value < 0:
        raise InvalidResults("measurements must be nonnegative finite numbers")
    try:
        finite = math.isfinite(value)
    except OverflowError:
        finite = False
    if not finite:
        raise InvalidResults("measurements must be nonnegative finite numbers")
    return value


def _flag(value):
    if type(value) is not bool:
        raise InvalidResults("correctness flags must be booleans")
    return value


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InvalidResults("duplicate JSON fields are not supported")
        result[key] = value
    return result


def _invalid_constant(_value):
    raise InvalidResults("nonfinite JSON constants are not supported")


def _read(root, relative, optional=False):
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise InvalidResults("input artifacts must remain inside the run root")
    try:
        return json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_invalid_constant,
        )
    except FileNotFoundError:
        if optional:
            return MISSING
        raise InvalidResults("a required input artifact is missing") from None
    except (OSError, UnicodeError, json.JSONDecodeError, RecursionError):
        raise InvalidResults("an input artifact cannot be read as JSON") from None


def _measured(rows, id_key):
    rows = _array(rows)
    measured, seen, repetitions, identifiers = [], set(), {}, set()
    for raw in rows:
        row = _object(raw)
        identifier = _identifier(row.get(id_key))
        identifiers.add(identifier)
        trial = row.get("trial")
        if type(trial) is not int or trial < -1:
            raise InvalidResults("trial numbers must be -1 or nonnegative integers")
        key = (identifier, trial)
        if key in seen:
            raise InvalidResults("duplicate query repetitions are not supported")
        seen.add(key)
        _number(row.get("milliseconds"))
        for field in COUNT_FIELDS:
            if field in row:
                _count(row[field])
        if trial >= 0:
            measured.append(row)
            repetitions.setdefault(identifier, set()).add(trial)
    if not measured or identifiers != set(repetitions):
        raise InvalidResults("every query needs measured trials")
    expected = next(iter(repetitions.values()))
    if min(expected) != 0 or max(expected) + 1 != len(expected):
        raise InvalidResults("measured repetitions must be contiguous from zero")
    if any(value != expected for value in repetitions.values()):
        raise InvalidResults("queries must have the same measured repetitions")
    return measured


def _timing(rows, id_key):
    values = sorted(row["milliseconds"] for row in rows)
    middle = len(values) // 2
    # Nonnegative subtraction avoids overflow when averaging large finite values.
    median = values[middle]
    if len(values) % 2 == 0:
        lower = values[middle - 1]
        median = lower + (median - lower) / 2
    return {
        "median_ms": _number(median),
        "p95_ms": values[(95 * len(values) + 99) // 100 - 1],
        "measured_trial_count": len(rows),
        "query_count": len({row[id_key] for row in rows}),
    }


def _successful_queries(rows, id_key, fields):
    successes = {}
    for row in rows:
        success = all(_flag(row.get(field)) for field in fields)
        identifier = row[id_key]
        successes[identifier] = successes.get(identifier, True) and success
    return sum(successes.values())


def _text_metrics(rows):
    measured = _measured(rows, "query_id")
    for row in rows:
        fp = _count(row.get("false_positive"))
        fn = _count(row.get("false_negative"))
        if _flag(row.get("exact")) != (fp == 0 and fn == 0):
            raise InvalidResults("exact flags must agree with false positives and negatives")
        if "true_positive" in row:
            tp = row["true_positive"]
            if "expected_count" in row and tp + fn != row["expected_count"]:
                raise InvalidResults("expected match counts are inconsistent")
            for field in ("match_count", "actual_count"):
                if field in row and tp + fp != row[field]:
                    raise InvalidResults("actual match counts are inconsistent")
    metrics = _timing(measured, "query_id")
    metrics["exact_query_count"] = _successful_queries(measured, "query_id", ("exact",))
    metrics["false_positive"] = sum(row["false_positive"] for row in measured)
    metrics["false_negative"] = sum(row["false_negative"] for row in measured)
    return metrics


def _unsupported(tool):
    print(
        f"{tool}: same-file caller exactness unsupported; "
        "required artifacts or a supported evidence schema are unavailable.",
        file=sys.stderr,
    )


def _complete_evidence(data):
    data = _object(data)
    for field in ("has_more", "truncated"):
        if field in data and _flag(data[field]):
            raise InvalidResults("incomplete saved evidence is not supported")
    return data


def _codebase_callers(root, task):
    identifier = _identifier(task.get("id"))
    if identifier in (".", "..") or "/" in identifier or "\\" in identifier:
        raise InvalidResults("evidence identifiers must be single filenames")
    raw = _object(_read(root, "codebase/full/evidence/" + identifier + ".json", True))
    search = _complete_evidence(raw.get("search_graph"))
    targets = set()
    for node in _array(search.get("results")):
        node = _object(node)
        path = _identifier(node.get("file_path"))
        qualified = _identifier(node.get("qualified_name"))
        if path == task["path"] and qualified.rsplit(".", 1)[-1] == task["symbol"]:
            targets.add(qualified)
    if not targets:
        return False, set()
    if len(targets) != 1:
        raise InvalidResults("ambiguous target evidence is not supported")
    target = next(iter(targets))
    if "." not in target:
        raise InvalidResults("unqualified caller evidence is not supported")
    prefix = target.rsplit(".", 1)[0]
    trace = _complete_evidence(raw.get("trace_path"))
    actual = set()
    for node in _array(trace.get("callers")):
        node = _object(node)
        name = _identifier(node.get("name"))
        qualified = _identifier(node.get("qualified_name"))
        if qualified.rsplit(".", 1)[-1] != name:
            raise InvalidResults("inconsistent caller evidence is not supported")
        if "file_path" in node and _identifier(node["file_path"]) != task["path"]:
            continue
        if qualified.rsplit(".", 1)[0] == prefix:
            actual.add(name)
    return True, actual


def _caller_metrics(root, tool, identifiers, data):
    relationships = _read(root, "relationships.json", True)
    if relationships is MISSING:
        _unsupported(tool)
        return None
    try:
        tasks = {}
        for task in _array(relationships):
            task = _object(task)
            identifier = _identifier(task.get("id"))
            if identifier in tasks:
                raise InvalidResults("duplicate relationship identifiers are not supported")
            _identifier(task.get("path"))
            _identifier(task.get("symbol"))
            tasks[identifier] = task
        edges = {}
        if tool == "graphify":
            for edge in _array(data.get("relationship_edges")):
                edge = _object(edge)
                identifier = _identifier(edge.get("id"))
                if identifier in edges:
                    raise InvalidResults("duplicate edge evidence is not supported")
                edges[identifier] = edge
        exact, fp, fn = 0, 0, 0
        for identifier in sorted(identifiers):
            if identifier not in tasks:
                raise InvalidResults("the caller oracle does not cover measured queries")
            task = tasks[identifier]
            expected = {
                _identifier(_object(caller).get("name"))
                for caller in _array(task.get("expected_callers"))
            }
            if tool == "codebase-memory-mcp":
                found, actual = _codebase_callers(root, task)
            else:
                edge = edges.get(identifier)
                if edge is None:
                    raise InvalidResults("saved edge evidence is missing")
                found = _flag(edge.get("target_found"))
                actual = {_identifier(name) for name in _array(edge.get("actual"))}
            exact += int(found and actual == expected)
            fp += len(actual - expected)
            fn += len(expected - actual)
        return {
            "evidence_query_count": len(identifiers),
            "exact_query_count": exact,
            "false_positive": fp,
            "false_negative": fn,
        }
    except InvalidResults:
        _unsupported(tool)
        return None


def _graph_metrics(root, tool, data):
    data = _object(data)
    if data.get("tool") != tool:
        raise InvalidResults("a graph artifact has an unsupported tool identifier")
    rows = _array(data.get("trials"))
    measured = _measured(rows, "id")
    kinds = {}
    success_fields = ("expected_file_found",) if tool == "codebase-memory-mcp" else (
        "expected_file_in_output", "symbol_in_output",
    )
    for row in rows:
        kind = row.get("kind")
        if kind not in ("symbol", "callers"):
            raise InvalidResults("graph trial kinds must be symbol or callers")
        if kinds.setdefault(row["id"], kind) != kind:
            raise InvalidResults("a graph query cannot change kind between repetitions")
        for field in success_fields:
            _flag(row.get(field))
    for field in ("mcp_initialize_seconds", "graph_load_seconds"):
        if field in data:
            _number(data[field])
    result = {}
    for kind in ("symbol", "callers"):
        subset = [row for row in measured if row["kind"] == kind]
        if not subset:
            continue
        metrics = _timing(subset, "id")
        if kind == "symbol":
            metrics["successful_trial_count"] = sum(
                all(row[field] for field in success_fields) for row in subset
            )
            metrics["successful_query_count"] = _successful_queries(subset, "id", success_fields)
        result["symbol_query" if kind == "symbol" else "caller_query"] = metrics
        if kind == "callers":
            callers = _caller_metrics(root, tool, {row["id"] for row in subset}, data)
            if callers is not None:
                result["same_file_callers"] = callers
    if tool == "codebase-memory-mcp" and "index" in data:
        index = _object(data["index"])
        if _count(index.get("returncode")) != 0:
            raise InvalidResults("a failed index run cannot be published")
        result["initial_index_seconds"] = _number(index.get("seconds"))
    return result


def build_summary(root):
    """Build a fresh public object. Input objects never become output values."""
    root = Path(root).resolve()
    manifest = _object(_read(root, "manifest.json"))
    files = _array(manifest.get("files"))
    repositories = _array(manifest.get("repositories"))
    repo_count = 0
    for repo in repositories:
        repo = _object(repo)
        if "commit" not in repo:
            raise InvalidResults("repository records must declare commit availability")
        if repo["commit"] is not None:
            _identifier(repo["commit"])
            repo_count += 1
    summary = {
        "schema_version": 1,
        "corpus": {
            "file_count": len(files),
            "byte_count": sum(_count(_object(entry).get("bytes")) for entry in files),
            "repo_count": repo_count,
        },
        "text": {},
    }
    text = _object(_read(root, "text-results.json"))
    groups = {}
    for row in _array(text.get("trials")):
        row = _object(row)
        tool = row.get("tool")
        if not isinstance(tool, str) or tool not in TEXT_TOOLS:
            raise InvalidResults("a text artifact has an unsupported tool identifier")
        groups.setdefault(tool, []).append(row)
    if not groups:
        raise InvalidResults("text results need measured trials")
    for tool in sorted(groups):
        summary["text"][tool] = _text_metrics(groups[tool])
    if "fff_initial_scan_seconds" in text:
        _number(text["fff_initial_scan_seconds"])
    patterns = _read(root, "ast-results.json", True)
    if patterns is not MISSING:
        patterns = _object(patterns)
        if patterns.get("tool") != "ast-grep":
            raise InvalidResults("the AST artifact has an unsupported tool identifier")
        rows = _array(patterns.get("trials"))
        if any(_object(row).get("tool") != "ast-grep" for row in rows):
            raise InvalidResults("the AST artifact has inconsistent tool identifiers")
        summary["ast_patterns"] = {"ast-grep": _text_metrics(rows)}
    mcp = _read(root, "fff/mcp-results.json", True)
    if mcp is not MISSING:
        mcp = _object(mcp)
        if mcp.get("tool") != "fff-mcp":
            raise InvalidResults("the MCP artifact has an unsupported tool identifier")
        rows = _array(mcp.get("trials"))
        if any("tool" in _object(row) and row["tool"] != "fff-mcp" for row in rows):
            raise InvalidResults("the MCP artifact has inconsistent tool identifiers")
        summary["text"]["fff-mcp"] = _text_metrics(rows)
        if "initialize_seconds" in mcp:
            _number(mcp["initialize_seconds"])
    graphs = {}
    for tool, relative in (
        ("codebase-memory-mcp", "codebase/full/query-results.json"),
        ("graphify", "graphify/query-results.json"),
    ):
        data = _read(root, relative, True)
        if data is not MISSING:
            graphs[tool] = _graph_metrics(root, tool, data)
    index = _read(root, "graphify/run-hcl/results.json", True)
    if index is not MISSING:
        index = _object(index)
        if index.get("tool") != "graphify":
            raise InvalidResults("the index artifact has an unsupported tool identifier")
        names = set()
        for raw in _array(index.get("runs")):
            run = _object(raw)
            seconds = _number(run.get("seconds"))
            if _count(run.get("returncode")) != 0:
                raise InvalidResults("a failed index run cannot be published")
            name = run.get("name")
            if name in ("initial-index", "unchanged-index"):
                if name in names:
                    raise InvalidResults("duplicate index runs are not supported")
                names.add(name)
                metrics = graphs.setdefault("graphify", {})
                field = "initial_index_seconds" if name == "initial-index" else "unchanged_index_seconds"
                metrics[field] = seconds
        if not names:
            raise InvalidResults("index results contain no supported measurements")
    if graphs:
        summary["graphs"] = graphs
    return summary


class _Parser(argparse.ArgumentParser):
    def error(self, _message):
        self.exit(2, "publish_results: invalid command line arguments\n")


def main(argv=None):
    parser = _Parser(prog="publish_results.py", description=__doc__)
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    temporary = None
    try:
        root = args.root.resolve()
        output = args.output.resolve()
        if output in {(root / relative).resolve() for relative in INPUT_FILES} or any(
            output.is_relative_to(root / relative)
            for relative in ("corpus", "codebase/full/evidence", "graphify/evidence")
        ):
            raise InvalidResults("the output must not replace private input artifacts")
        serialized = json.dumps(build_summary(root), indent=2, sort_keys=True, allow_nan=False) + "\n"
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=output.parent, delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(serialized)
        os.replace(temporary, output)
        temporary = None
    except InvalidResults as error:
        print("publish_results: " + str(error), file=sys.stderr)
        return 2
    except (OSError, ValueError, OverflowError, RuntimeError):
        print("publish_results: export failed; check input and output artifacts", file=sys.stderr)
        return 2
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                print("publish_results: temporary output cleanup failed", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
