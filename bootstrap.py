#!/usr/bin/env python3
"""Install pinned benchmark tools locally; does not change agent configuration."""

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

BASE = Path(__file__).resolve().parent
RELEASE = "https://github.com/dmtrKovalenko/fff/releases/download/v0.11.0/"


def main():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit(
            "This pinned bundle targets macOS arm64. Select and verify the equivalent platform assets before running elsewhere."
        )
    metadata = {}
    locked = json.loads((BASE / "tool-lock.json").read_text())["assets"]
    tools = BASE / "tools"
    tools.mkdir(exist_ok=True)
    for asset in locked:
        if not asset["name"].endswith((".tar.gz", ".zip")):
            continue
        archive_path = tools / asset["name"]
        if not archive_path.exists():
            urllib.request.urlretrieve(asset["url"], archive_path)
        if hashlib.sha256(archive_path.read_bytes()).hexdigest() != asset["sha256"]:
            raise RuntimeError("Checksum mismatch: " + asset["name"])
        if asset["name"].endswith(".zip"):
            target = tools / "ast-grep"
            with zipfile.ZipFile(archive_path) as archive:
                for name in archive.namelist():
                    if not (target / name).resolve().is_relative_to(target.resolve()):
                        raise RuntimeError("Unsafe ZIP member")
                archive.extractall(target)
            for binary in target.iterdir():
                if binary.is_file():
                    binary.chmod(0o755)
        else:
            with tarfile.open(archive_path) as archive:
                archive.extractall(tools, filter="data")
        metadata[asset["name"]] = asset

    for asset, dest in [
        ("fff-mcp-aarch64-apple-darwin", BASE / "fff/fff-mcp"),
        (
            "fff_search-0.11.0-cp310-abi3-macosx_11_0_arm64.whl",
            BASE / "fff/fff_search-0.11.0-cp310-abi3-macosx_11_0_arm64.whl",
        ),
    ]:
        with urllib.request.urlopen(
            RELEASE + asset + ".sha256", timeout=30
        ) as response:
            expected = response.read().decode().split()[0]
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            urllib.request.urlretrieve(RELEASE + asset, dest)
        actual = hashlib.sha256(dest.read_bytes()).hexdigest()
        pinned = next(a["sha256"] for a in locked if a["name"] == asset)
        if actual != expected or actual != pinned:
            raise RuntimeError("Checksum mismatch: " + asset)
        metadata[asset] = {"url": RELEASE + asset, "sha256": actual}
        if asset.endswith(".whl"):
            sdk = BASE / "fff/sdk"
            with zipfile.ZipFile(dest) as archive:
                for name in archive.namelist():
                    if not (sdk / name).resolve().is_relative_to(sdk.resolve()):
                        raise RuntimeError("Unsafe wheel member")
                archive.extractall(sdk)
        else:
            dest.chmod(0o755)
    uv = shutil.which("uv")
    if not uv:
        raise SystemExit("uv is required to create the isolated Graphify environment")
    cache = subprocess.check_output([uv, "cache", "dir"], text=True).strip()
    env = {
        "PATH": os.environ.get("PATH", os.defpath),
        "UV_CACHE_DIR": cache,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
    }
    venv = BASE / "graphify/.venv"
    if not venv.exists():
        subprocess.run([uv, "venv", "--python", "3.13", str(venv)], env=env, check=True)
    subprocess.run(
        [
            uv,
            "pip",
            "sync",
            "--python",
            str(venv / "bin/python"),
            str(BASE / "graphify/requirements.lock"),
        ],
        env=env,
        check=True,
    )
    binary = tools / "codebase-memory-mcp"
    rg = str(tools / "ripgrep-15.2.0-aarch64-apple-darwin/rg")
    metadata["ripgrep"] = {
        "path": rg,
        "sha256": hashlib.sha256(Path(rg).read_bytes()).hexdigest(),
    }
    metadata["codebase-memory-mcp"] = {
        "path": str(binary),
        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "version": subprocess.check_output(
            [str(binary), "--version"], text=True, env={"PATH": os.defpath}
        ).strip(),
    }
    (BASE / "tools.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("Pinned tools ready; existing agent configuration was not changed.")


if __name__ == "__main__":
    main()
