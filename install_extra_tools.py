#!/usr/bin/env python3
"""Build the locked GNU grep and ugrep sources without changing global tools."""

import hashlib
import json
from pathlib import Path
import subprocess
import tarfile
import urllib.request

BASE = Path(__file__).resolve().parent


def main():
    tools = BASE / "tools"
    tools.mkdir(exist_ok=True)
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "LC_ALL": "C"}
    for item in json.loads((BASE / "tool-lock.json").read_text())["source_builds"]:
        name = item["name"]
        if name not in {"grep", "ugrep"}:
            raise ValueError("Unsupported source build")
        archive_path = tools / (name + ".tar")
        if not archive_path.exists():
            urllib.request.urlretrieve(item["url"], archive_path)
        if hashlib.sha256(archive_path.read_bytes()).hexdigest() != item["sha256"]:
            raise RuntimeError("Source checksum mismatch")
        build = tools / ("build-" + name)
        build.mkdir(exist_ok=True)
        with tarfile.open(archive_path) as archive:
            archive.extractall(build, filter="data")
        directories = [p for p in build.iterdir() if p.is_dir()]
        if len(directories) != 1:
            raise RuntimeError("Expected one source directory")
        commands = [["./configure", "--prefix=" + str(tools / name)]]
        if name == "grep":
            commands[0].append("--disable-nls")
        commands += [["make", "-j4"], ["make", "install"]]
        with (tools / (name + "-build.log")).open("w") as log:
            for command in commands:
                subprocess.run(
                    ["/usr/bin/sandbox-exec", "-p", "(version 1)(allow default)(deny network*)", *command],
                    cwd=directories[0], env=env, stdout=log, stderr=log, check=True,
                )
        print(name + " installed locally")


if __name__ == "__main__":
    main()
