"""Structural-pattern checks use only this public fixture and mocked CLI output."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import ast_bench

SOURCE = '''label = "é🐍"; target(0)
def outer():
    def inner(): return target(target(1))
    return lambda: target("λ")
obj.target(2)
'''.encode()


class AstBenchTests(unittest.TestCase):
    def test_unicode_nested_and_lambda_byte_offsets(self):
        snippets = [b"target(0)", b"target(target(1))", b"target(1)", 'target("λ")'.encode()]
        expected = {(SOURCE.index(s), SOURCE.index(s) + len(s)) for s in snippets}
        self.assertEqual(ast_bench.oracle(SOURCE, "target"), expected)
        payload = json.dumps([{"range": {"byteOffset": {"start": s, "end": e}},
                               "text": "PRIVATE_SENTINEL"} for s, e in expected]).encode()
        with patch.object(ast_bench.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, payload)) as run:
            self.assertEqual(ast_bench.search("/bin/ast-grep", Path("/public.py"), "target", 2),
                             (expected, len(payload)))
        self.assertEqual(run.call_args.args[0], ["/bin/ast-grep", "run", "--lang", "python",
                         "--pattern", "target($$$ARGS)", "--json=compact", "/public.py"])
        self.assertEqual(run.call_args.kwargs["timeout"], 2)

    def test_failed_or_malformed_child_output_is_rejected(self):
        for status, output in [(2, b"PRIVATE_SENTINEL"), (0, b"bad JSON"), (0, b"{}"),
                               (0, b"[{}]"), (0, b'[{"range":{"byteOffset":{"start":true,"end":2}}}]')]:
            with self.subTest(status=status, output=output), patch.object(
                ast_bench.subprocess, "run", return_value=subprocess.CompletedProcess([], status, output)
            ), self.assertRaises((ValueError, KeyError, TypeError)):
                ast_bench.search("binary", Path("/public.py"), "target", 2)
        with patch.object(ast_bench.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, b"[]")):
            self.assertEqual(ast_bench.search("binary", Path("/public.py"), "target", 2), (set(), 2))

    def test_warmup_repeats_and_numeric_only_output(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(ast_bench, "BASE", Path(folder)):
            root = Path(folder)
            (root / "corpus").mkdir()
            (root / "corpus/public.py").write_bytes(SOURCE)
            (root / "relationships.json").write_text(json.dumps([
                {"id": "task-0", "path": "public.py", "symbol": "target", "expected_callers": []}]))
            with patch.object(ast_bench, "search", return_value=(ast_bench.oracle(SOURCE, "target"), 99)) as search:
                self.assertEqual(ast_bench.main(["--repeats", "2"]), 0)
            data = json.loads((root / "ast-results.json").read_text())
            self.assertEqual(data["tool"], "ast-grep")
            self.assertEqual(search.call_count, 3)
            self.assertEqual([r["trial"] for r in data["trials"]], [-1, 0, 1])
            self.assertEqual(set(data["trials"][0]), {"tool", "query_id", "trial", "milliseconds", "exact",
                             "false_positive", "false_negative", "true_positive", "expected_count", "match_count", "output_bytes"})
            self.assertTrue(all(r["exact"] and r["true_positive"] == 4 for r in data["trials"]))
            with contextlib.redirect_stderr(io.StringIO()):
                for arguments in (["--repeats", "0"], ["--repeats", "-1"], ["--timeout", "nan"]):
                    with self.assertRaises(SystemExit):
                        ast_bench.main(arguments)
                with patch.object(ast_bench, "search", side_effect=subprocess.TimeoutExpired("PRIVATE_SENTINEL", 1)):
                    self.assertEqual(ast_bench.main([]), 2)


if __name__ == "__main__":
    unittest.main()
