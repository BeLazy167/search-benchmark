#!/usr/bin/env python3
"""Independent Python AST oracle for direct, same-file top-level named calls."""

import ast
from collections import Counter
import hashlib
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent


class Calls(ast.NodeVisitor):
    def __init__(self):
        self.names = set()

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            self.names.add(node.func.id)
        self.generic_visit(node)

    # A call inside a nested function belongs to that nested scope.
    def visit_FunctionDef(self, node):
        pass

    def visit_AsyncFunctionDef(self, node):
        pass

    def visit_ClassDef(self, node):
        pass

    def visit_Lambda(self, node):
        pass


def main():
    choices = []
    for f in (BASE / "corpus").rglob("*.py"):
        rel = f.relative_to(BASE / "corpus").as_posix()
        if "/tests/" in rel or "/test/" in rel:
            continue
        try:
            tree = ast.parse(f.read_text())
        except SyntaxError:
            continue
        funcs = {
            n.name: n
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        found = {}
        for name, node in funcs.items():
            visitor = Calls()
            for statement in node.body:
                visitor.visit(statement)
            found[name] = visitor.names
        for name, target in funcs.items():
            if len(name) < 8 or name.startswith("_"):
                continue
            callers = [
                {"name": c, "line": n.lineno}
                for c, n in funcs.items()
                if c != name and name in found[c]
            ]
            if callers:
                choices.append(
                    {
                        "id": "",
                        "symbol": name,
                        "path": rel,
                        "line": target.lineno,
                        "expected_callers": callers,
                    }
                )
    choices.sort(
        key=lambda q: hashlib.sha256((q["path"] + q["symbol"]).encode()).hexdigest()
    )
    chosen = []
    counts = Counter()
    for q in choices:
        repo = q["path"].split("/")[0]
        if counts[repo] < 2 and len(chosen) < 12:
            q["id"] = f"callers-{len(chosen):02d}"
            chosen.append(q)
            counts[repo] += 1
    (BASE / "relationships.json").write_text(json.dumps(chosen, indent=2) + "\n")
    print("caller tasks", len(chosen), "repos", len(counts))


if __name__ == "__main__":
    main()
