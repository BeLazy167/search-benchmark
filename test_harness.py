import ast
import unittest
from unittest.mock import patch
from build_relationships import Calls
from prepare import allowed
from qa_pilot import parse_callers, score


class HarnessTests(unittest.TestCase):
    def test_local_rerun_does_not_make_model_requests(self):
        import contextlib
        import io
        import run_all

        commands = []
        with (
            patch("sys.argv", ["run_all.py"]),
            patch(
                "subprocess.run",
                side_effect=lambda command, **kwargs: commands.append(command),
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            run_all.main()
        self.assertFalse(
            any(
                any(str(arg).endswith("qa_pilot.py") for arg in command)
                for command in commands
            )
        )
        fuzzy = next(
            command
            for command in commands
            if any(str(arg).endswith("fuzzy_bench.py") for arg in command)
        )
        self.assertNotEqual(fuzzy[0], "/usr/bin/sandbox-exec")
        # The fff runner applies its own sandbox to its MCP child.

    def test_direct_calls_exclude_nested_scopes_and_strings(self):
        node = ast.parse("""def caller():
    target_function()
    "fake_function()"
    # comment_function()
    def inner():
        nested_function()
    thunk = lambda: lambda_function()
""").body[0]
        visitor = Calls()
        for statement in node.body:
            visitor.visit(statement)
        self.assertEqual(visitor.names, {"target_function"})

    def test_credential_paths_are_outside_corpus(self):
        for path in [
            ".env",
            "config/.env.local",
            "credentials.json",
            "service-account.private-key.json",
            "node_modules/pkg/main.py",
        ]:
            self.assertFalse(allowed(path), path)
        self.assertTrue(allowed("src/auth/session.py"))

    def test_answer_grading_is_set_based(self):
        self.assertEqual(
            parse_callers('```json\n{"callers":["a","a"]}\n```'), (["a"], None)
        )
        self.assertTrue(score(["a", "b"], ["b", "a"])[0])
        self.assertFalse(score(["a"], ["a", "b"])[0])
        self.assertIsNotNone(parse_callers("not JSON")[1])


if __name__ == "__main__":
    unittest.main()
