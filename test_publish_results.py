"""Public exporter checks using synthetic private artifacts, never real source."""

import contextlib
import copy
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import publish_results


PRIVATE = "PRIVATE_SENTINEL_do_not_publish_7ab13"
TEXT_FIELDS = {
    "median_ms", "p95_ms", "measured_trial_count", "query_count",
    "exact_query_count", "false_positive", "false_negative",
}
TIMING_FIELDS = {"median_ms", "p95_ms", "measured_trial_count", "query_count"}
CALLER_FIELDS = {"evidence_query_count", "exact_query_count", "false_positive", "false_negative"}


class PublishResultsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix=PRIVATE)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.manifest = {
            "corpus_sha256": PRIVATE,
            "repositories": [
                {"name": PRIVATE, "commit": PRIVATE},
                {"name": PRIVATE + "_omitted", "commit": None},
            ],
            "files": [
                {"path": PRIVATE + "/module.py", "bytes": 100, "sha256": PRIVATE},
                {"path": PRIVATE + "/other.py", "bytes": 23, "sha256": PRIVATE},
            ],
            "policy": {PRIVATE: PRIVATE},
        }
        self.text = {
            "platform": PRIVATE, "versions": {PRIVATE: PRIVATE},
            "commands": {"ripgrep": [PRIVATE]}, "corpus_sha256": PRIVATE,
            "prompt": PRIVATE, "source": PRIVATE, PRIVATE: {PRIVATE: [PRIVATE]},
            "trials": [
                self.text_row("a", -1, 9000, fp=99, fn=77),
                self.text_row("b", -1, 9000, fp=99, fn=77),
                self.text_row("a", 0, 1), self.text_row("b", 0, 2),
                self.text_row("a", 1, 3, fp=2, fn=1), self.text_row("b", 1, 4),
            ],
        }
        self.write("manifest.json", self.manifest)
        self.write("text-results.json", self.text)

    def write(self, relative, data):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")

    def text_row(self, query, trial, milliseconds, fp=0, fn=0, tool="ripgrep"):
        return {
            "tool": tool, "query_id": PRIVATE + query, "query": PRIVATE,
            "trial": trial, "milliseconds": milliseconds,
            "false_positive": fp, "false_negative": fn, "exact": fp == fn == 0,
            "output_bytes": 50, "pages": 1,
            "extra_examples": [[PRIVATE, 1]], "missing_examples": [[PRIVATE, 2]],
            "stdout": PRIVATE, "stderr": PRIVATE, "source": PRIVATE,
            "model_prompt": PRIVATE, PRIVATE: [PRIVATE, {PRIVATE: PRIVATE}],
        }

    def cli(self, *extra):
        return subprocess.run(
            [sys.executable, "-B", str(Path(publish_results.__file__).resolve()),
             "--root", str(self.root), "--output", str(self.root / "public.json"), *extra],
            capture_output=True, text=True, check=False,
        )

    def seed_graphs(self):
        caller_id = PRIVATE + "_callers"
        symbol_id = PRIVATE + "_symbol"
        path = PRIVATE + "/module.py"
        symbol = PRIVATE + "_target"
        caller = PRIVATE + "_caller"
        self.write("relationships.json", [{
            "id": caller_id, "path": path, "symbol": symbol,
            "line": 10, "expected_callers": [{"name": caller, "line": 20}],
            "source": PRIVATE,
        }])
        evidence = {
            "search_graph": {"has_more": False, "results": [{
                "name": symbol, "file_path": path,
                "qualified_name": PRIVATE + ".module." + symbol, "source": PRIVATE,
            }]},
            "trace_path": {"callers": [
                {"name": caller, "qualified_name": PRIVATE + ".module." + caller},
                {"name": PRIVATE + "_external", "qualified_name": PRIVATE + ".other." + PRIVATE + "_external"},
                {"name": PRIVATE + "_different_file", "file_path": PRIVATE + "/other.py",
                 "qualified_name": PRIVATE + ".module." + PRIVATE + "_different_file"},
            ]},
            "stdout": PRIVATE, "stderr": PRIVATE, "prompt": PRIVATE,
        }
        self.evidence_file = "codebase/full/evidence/" + caller_id + ".json"
        self.write(self.evidence_file, evidence)
        self.codebase = {"tool": "codebase-memory-mcp", "version": PRIVATE, "trials": [],
                         "index": {"seconds": 0.25, "returncode": 0, "command": [PRIVATE], "env": {PRIVATE: PRIVATE}}}
        self.graphify = {"tool": "graphify", "graph_load_seconds": 0.1, "trials": [],
                         "interface": PRIVATE, "relationship_edges": [{
                             "id": caller_id, "target_found": True,
                             "actual": [caller], "expected": [PRIVATE + "_wrong"], "exact": False,
                         }]}
        for trial in (-1, 0, 1):
            for kind, identifier in (("symbol", symbol_id), ("callers", caller_id)):
                base = {"id": identifier, "kind": kind, "trial": trial,
                        "milliseconds": 9000 if trial == -1 else trial + 1,
                        "output_bytes": 100, "source": PRIVATE}
                cbm = dict(base, expected_file_found=trial == 0 or kind == "callers")
                graph = dict(base, expected_file_in_output=trial >= 0, symbol_in_output=True)
                self.codebase["trials"].append(cbm)
                self.graphify["trials"].append(graph)
        self.write("codebase/full/query-results.json", self.codebase)
        self.write("graphify/query-results.json", self.graphify)
        self.write("graphify/run-hcl/results.json", {
            "tool": "graphify", "commit": PRIVATE, "corpus": PRIVATE,
            "runs": [
                {"name": "unchanged-index", "seconds": 0.5, "returncode": 0, "command": [PRIVATE]},
                {"name": "initial-index", "seconds": 5, "returncode": 0, "stdout": PRIVATE},
            ],
            "index": {"relations": {PRIVATE: 1}, "source_files": [PRIVATE]},
        })

    def assert_numeric_tree(self, value):
        if isinstance(value, dict):
            for child in value.values():
                self.assert_numeric_tree(child)
        else:
            self.assertIn(type(value), (int, float))
            self.assertGreaterEqual(value, 0)

    def test_warmup_excluded_and_one_failed_repeat_makes_query_nonexact(self):
        result = publish_results.build_summary(self.root)
        self.assertEqual(result, {
            "schema_version": 1,
            "corpus": {"file_count": 2, "byte_count": 123, "repo_count": 1},
            "text": {"ripgrep": {
                "median_ms": 2.5, "p95_ms": 4, "measured_trial_count": 4,
                "query_count": 2, "exact_query_count": 1,
                "false_positive": 2, "false_negative": 1,
            }},
        })
        self.assertNotIn(PRIVATE, json.dumps(result))
        self.assert_numeric_tree(result)

    def test_p95_uses_nearest_rank(self):
        self.text["trials"] = [self.text_row("one", trial, trial + 1) for trial in range(21)]
        self.write("text-results.json", self.text)
        metrics = publish_results.build_summary(self.root)["text"]["ripgrep"]
        self.assertEqual(metrics["p95_ms"], 20)
        self.assertEqual(metrics["median_ms"], 11)

    def test_each_allowlisted_text_tool_gets_its_own_aggregate(self):
        self.text["trials"] = [self.text_row("one", 0, 1, tool=tool) for tool in publish_results.TEXT_TOOLS]
        self.write("text-results.json", self.text)
        result = publish_results.build_summary(self.root)
        self.assertEqual(set(result["text"]), publish_results.TEXT_TOOLS)
        for metrics in result["text"].values():
            self.assertEqual(set(metrics), TEXT_FIELDS)
            self.assertEqual(metrics["query_count"], 1)

    def test_optional_mcp_and_graphs_publish_only_fixed_schema_and_numbers(self):
        self.seed_graphs()
        mcp_rows = [dict(row) for row in self.text["trials"]]
        for row in mcp_rows:
            del row["tool"]
        self.write("fff/mcp-results.json", {"tool": "fff-mcp", "version": PRIVATE,
                                           "initialize_seconds": 0.2, "trials": mcp_rows})
        completed = self.cli()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        serialized = (self.root / "public.json").read_text()
        self.assertNotIn(PRIVATE, serialized + completed.stdout + completed.stderr)
        result = json.loads(serialized)
        self.assertEqual(set(result), {"schema_version", "corpus", "text", "graphs"})
        self.assertEqual(set(result["text"]), {"ripgrep", "fff-mcp"})
        self.assertEqual(set(result["graphs"]), {"codebase-memory-mcp", "graphify"})
        for metrics in result["text"].values():
            self.assertEqual(set(metrics), TEXT_FIELDS)
        for graph in result["graphs"].values():
            self.assertEqual(set(graph["symbol_query"]), TIMING_FIELDS | {"successful_trial_count", "successful_query_count"})
            self.assertEqual(set(graph["caller_query"]), TIMING_FIELDS)
            self.assertEqual(set(graph["same_file_callers"]), CALLER_FIELDS)
            self.assertEqual(graph["same_file_callers"], {
                "evidence_query_count": 1, "exact_query_count": 1,
                "false_positive": 0, "false_negative": 0,
            })
        cbm = result["graphs"]["codebase-memory-mcp"]
        self.assertEqual(set(cbm), {"symbol_query", "caller_query", "same_file_callers", "initial_index_seconds"})
        self.assertEqual(cbm["symbol_query"]["successful_trial_count"], 1)
        self.assertEqual(cbm["symbol_query"]["successful_query_count"], 0)
        graphify = result["graphs"]["graphify"]
        self.assertEqual(set(graphify), {"symbol_query", "caller_query", "same_file_callers", "initial_index_seconds", "unchanged_index_seconds"})
        self.assertEqual(graphify["symbol_query"]["successful_query_count"], 1)
        self.assertEqual(graphify["initial_index_seconds"], 5)
        self.assertEqual(graphify["unchanged_index_seconds"], 0.5)
        self.assert_numeric_tree(result)

    def test_graphify_callers_compare_actual_with_ast_oracle_not_saved_exact(self):
        self.seed_graphs()
        edge = self.graphify["relationship_edges"][0]
        edge.update(actual=[PRIVATE + "_wrong"], exact=True)
        self.write("graphify/query-results.json", self.graphify)
        metrics = publish_results.build_summary(self.root)["graphs"]["graphify"]["same_file_callers"]
        self.assertEqual(metrics, {"evidence_query_count": 1, "exact_query_count": 0,
                                   "false_positive": 1, "false_negative": 1})

    def test_missing_target_is_not_exact_even_for_empty_oracle(self):
        self.seed_graphs()
        relationships = json.loads((self.root / "relationships.json").read_text())
        relationships[0]["expected_callers"] = []
        self.write("relationships.json", relationships)
        self.write(self.evidence_file, {"search_graph": {"results": []}})
        metrics = publish_results.build_summary(self.root)["graphs"]["codebase-memory-mcp"]["same_file_callers"]
        self.assertEqual(metrics["exact_query_count"], 0)

    def test_missing_optional_artifacts_omit_sections(self):
        result = publish_results.build_summary(self.root)
        self.assertNotIn("graphs", result)
        self.assertNotIn("ast_patterns", result)
        self.assertNotIn("fff-mcp", result["text"])

    def test_optional_ast_patterns_export_only_aggregate_numbers(self):
        self.write("ast-results.json", {"tool": "ast-grep", "source": PRIVATE, "trials": [
            self.text_row("one", -1, 999, tool="ast-grep"),
            self.text_row("one", 0, 2, tool="ast-grep"),
        ]})
        completed = self.cli()
        self.assertEqual(completed.returncode, 0, completed.stderr)
        serialized = (self.root / "public.json").read_text()
        self.assertNotIn(PRIVATE, serialized + completed.stdout + completed.stderr)
        result = json.loads(serialized)
        self.assertEqual(result["ast_patterns"], {"ast-grep": {
            "median_ms": 2, "p95_ms": 2, "measured_trial_count": 1, "query_count": 1,
            "exact_query_count": 1, "false_positive": 0, "false_negative": 0,
        }})
        self.assert_numeric_tree(result)

    def test_ast_tool_sentinels_are_rejected_without_leaks(self):
        for top, row in ((PRIVATE, "ast-grep"), ("ast-grep", PRIVATE), ("ast-grep", None)):
            self.write("ast-results.json", {"tool": top, "trials": [self.text_row("one", 0, 1, tool=row)]})
            completed = self.cli()
            self.assertEqual(completed.returncode, 2)
            self.assertNotIn(PRIVATE, completed.stdout + completed.stderr)
            self.assertFalse((self.root / "public.json").exists())

    def test_missing_or_unknown_evidence_reports_unsupported_without_private_text(self):
        for evidence in (None, {"search_graph": {"renamed_results": PRIVATE}},
                         {"search_graph": {"results": [], "has_more": True}}):
            with self.subTest(evidence=evidence):
                self.seed_graphs()
                if evidence is None:
                    (self.root / self.evidence_file).unlink()
                else:
                    self.write(self.evidence_file, evidence)
                stderr = io.StringIO()
                with contextlib.redirect_stderr(stderr):
                    result = publish_results.build_summary(self.root)
                self.assertNotIn("same_file_callers", result["graphs"]["codebase-memory-mcp"])
                self.assertIn("unsupported", stderr.getvalue())
                self.assertNotIn(PRIVATE, json.dumps(result) + stderr.getvalue())

    def test_missing_relationships_does_not_claim_caller_success(self):
        self.seed_graphs()
        (self.root / "relationships.json").unlink()
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            result = publish_results.build_summary(self.root)
        for graph in result["graphs"].values():
            self.assertNotIn("same_file_callers", graph)
        self.assertEqual(stderr.getvalue().count("unsupported"), 2)

    def test_malformed_nonfinite_and_negative_measurements_are_rejected(self):
        cases = [("milliseconds", value) for value in (-1, float("nan"), float("inf"), -float("inf"), True, "1", None)]
        cases += [("false_positive", -1), ("false_negative", 1.5), ("output_bytes", True),
                  ("pages", -1), ("trial", -2), ("trial", True), ("exact", 1)]
        for field, value in cases:
            with self.subTest(field=field, value=value):
                data = copy.deepcopy(self.text)
                data["trials"][2][field] = value
                self.write("text-results.json", data)
                with self.assertRaises(publish_results.InvalidResults):
                    publish_results.build_summary(self.root)

    def test_nonfinite_exponent_and_duplicate_json_fields_are_rejected(self):
        path = self.root / "text-results.json"
        original = path.read_text()
        path.write_text(original.replace('"milliseconds": 1,', '"milliseconds": 1e999,', 1))
        with self.assertRaises(publish_results.InvalidResults):
            publish_results.build_summary(self.root)
        path.write_text('{"trials": [], "trials": []}')
        with self.assertRaises(publish_results.InvalidResults):
            publish_results.build_summary(self.root)

    def test_empty_duplicate_and_incomplete_measured_trials_are_rejected(self):
        cases = [[], self.text["trials"][:2], self.text["trials"][:-1],
                 self.text["trials"] + [self.text["trials"][2]]]
        for rows in cases:
            with self.subTest(rows=rows):
                self.write("text-results.json", {"trials": rows})
                with self.assertRaises(publish_results.InvalidResults):
                    publish_results.build_summary(self.root)

    def test_inconsistent_exact_or_match_counts_are_rejected(self):
        for extra in ({"exact": False}, {"false_positive": 1},
                      {"true_positive": 1, "expected_count": 2}):
            with self.subTest(extra=extra):
                data = copy.deepcopy(self.text)
                data["trials"][2].update(extra)
                self.write("text-results.json", data)
                with self.assertRaises(publish_results.InvalidResults):
                    publish_results.build_summary(self.root)

    def test_unknown_tool_is_rejected_without_echoing_it(self):
        self.text["trials"][0]["tool"] = PRIVATE
        self.write("text-results.json", self.text)
        completed = self.cli()
        self.assertEqual(completed.returncode, 2)
        self.assertNotIn(PRIVATE, completed.stdout + completed.stderr)
        self.assertFalse((self.root / "public.json").exists())

    def test_malformed_optional_artifact_is_rejected(self):
        for relative in ("ast-results.json", "fff/mcp-results.json", "codebase/full/query-results.json",
                         "graphify/query-results.json", "graphify/run-hcl/results.json"):
            with self.subTest(relative=relative):
                self.write(relative, None)
                with self.assertRaises(publish_results.InvalidResults):
                    publish_results.build_summary(self.root)
                (self.root / relative).unlink()

    def test_invalid_or_failed_index_measurements_are_rejected(self):
        self.seed_graphs()
        original = copy.deepcopy(self.codebase)
        for update in ({"seconds": -1}, {"seconds": float("inf")}, {"returncode": 1}):
            with self.subTest(update=update):
                self.codebase = copy.deepcopy(original)
                self.codebase["index"].update(update)
                self.write("codebase/full/query-results.json", self.codebase)
                with self.assertRaises(publish_results.InvalidResults):
                    publish_results.build_summary(self.root)

    def test_invalid_manifest_byte_count_is_rejected(self):
        for value in (-1, 1.5, True, PRIVATE):
            with self.subTest(value=value):
                self.manifest["files"][0]["bytes"] = value
                self.write("manifest.json", self.manifest)
                with self.assertRaises(publish_results.InvalidResults):
                    publish_results.build_summary(self.root)

    def test_cli_failure_preserves_existing_output_and_hides_paths(self):
        output = self.root / "public.json"
        output.write_text("previous valid public export\n")
        (self.root / "text-results.json").write_text(PRIVATE)
        completed = self.cli()
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(output.read_text(), "previous valid public export\n")
        self.assertNotIn(PRIVATE, completed.stdout + completed.stderr)
        self.assertNotIn("Traceback", completed.stderr)

    def test_cli_argument_errors_do_not_echo_private_arguments(self):
        completed = self.cli("--unknown-" + PRIVATE, PRIVATE)
        self.assertEqual(completed.returncode, 2)
        self.assertNotIn(PRIVATE, completed.stdout + completed.stderr)

    def test_cli_refuses_to_overwrite_input_artifacts(self):
        for relative in ("manifest.json", "ast-results.json"):
            path = self.root / relative
            if relative == "ast-results.json":
                path.write_text(PRIVATE)
            before = path.read_bytes()
            stderr = io.StringIO()
            with contextlib.redirect_stderr(stderr):
                status = publish_results.main(["--root", str(self.root), "--output", str(path)])
            self.assertEqual(status, 2)
            self.assertEqual(path.read_bytes(), before)
            self.assertNotIn(PRIVATE, stderr.getvalue())

    def test_input_symlinks_cannot_escape_private_run_root(self):
        target = self.root.parent / (PRIVATE + ".json")
        target.write_text("{}")
        self.addCleanup(target.unlink, missing_ok=True)
        path = self.root / "text-results.json"
        path.unlink()
        path.symlink_to(target)
        with self.assertRaises(publish_results.InvalidResults):
            publish_results.build_summary(self.root)


if __name__ == "__main__":
    unittest.main()
