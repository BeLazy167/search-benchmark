#!/usr/bin/env python3
"""Run a benchmark without network, home-directory access, or inherited credentials."""

import os
from pathlib import Path
import shutil
import subprocess
import sys


def main():
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python3 offline.py COMMAND [ARG ...]")
    sandbox = shutil.which("sandbox-exec")
    if not sandbox:
        raise SystemExit("This runner requires macOS sandbox-exec")
    command = sys.argv[1:]
    local_ipc = command[0] == "--local-ipc"
    if local_ipc:
        command = command[1:]
    if not command:
        raise SystemExit("A command is required")
    root = Path(__file__).resolve().parent
    # SBPL string escaping, not shell quoting. The command never uses a shell.
    home_path = str(Path.home()).replace("\\", "\\\\").replace('"', '\\"')
    profile = (
        '(version 1)(allow default)'
        + ('(deny network* (local ip "*:*") (remote ip "*:*"))' if local_ipc else '(deny network*)')
        +
        f'(deny file-read* file-write* (subpath "{home_path}"))'
    )
    isolated = root / "offline-state"
    isolated.mkdir(exist_ok=True, mode=0o700)
    env = {
        "PATH": os.pathsep.join([str(root / "tools/ripgrep-15.2.0-aarch64-apple-darwin"), str(root / "tools"), "/usr/bin", "/bin"]),
        "LC_ALL": "C",
        "XDG_CONFIG_HOME": str(isolated / "config"),
        "XDG_CACHE_HOME": str(isolated / "cache"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "SEARCH_BENCHMARK_OFFLINE": "1",
        "GRAPHIFY_QUERY_LOG_DISABLE": "1",
    }
    os.umask(0o077)
    result = subprocess.run([sandbox, "-p", profile, *command], env=env, cwd=root)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
