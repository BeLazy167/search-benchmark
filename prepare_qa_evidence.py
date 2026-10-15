#!/usr/bin/env python3
"""Capture actual tool evidence for a blind fixed-evidence QA pilot."""

import json
from pathlib import Path
import shutil
import subprocess

BASE = Path(__file__).resolve().parent


def main():
    tasks = json.loads((BASE / "relationships.json").read_text())
    for tool in ["ripgrep", "grep", "codebase", "graphify"]:
        out = BASE / "qa-evidence" / tool
        out.mkdir(parents=True, exist_ok=True)
        for task in tasks:
            if tool in ("ripgrep", "grep"):
                binary = (
                    (
                        shutil.which("rg")
                        or json.loads((BASE / "tools.json").read_text())["ripgrep"][
                            "path"
                        ]
                    )
                    if tool == "ripgrep"
                    else "/usr/bin/grep"
                )
                command = [
                    binary,
                    "-n",
                    "-H",
                    "-F",
                    "-B",
                    "40",
                    "-A",
                    "5",
                    "--",
                    task["symbol"],
                    task["path"],
                ]
                proc = subprocess.run(
                    command,
                    cwd=BASE / "corpus",
                    env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
                    capture_output=True,
                    text=True,
                )
                if proc.returncode not in (0, 1):
                    raise RuntimeError(proc.stderr)
                text = proc.stdout
            elif tool == "codebase":
                raw = json.loads(
                    (
                        BASE / "codebase/full/evidence" / (task["id"] + ".json")
                    ).read_text()
                )
                text = json.dumps(raw, indent=2)
            else:
                text = (BASE / "graphify/evidence" / (task["id"] + ".txt")).read_text()
            (out / (task["id"] + ".txt")).write_text(text)
    print("Evidence written. fff-mcp evidence is produced by fff_mcp_bench.py.")


if __name__ == "__main__":
    main()
