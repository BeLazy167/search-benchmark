#!/usr/bin/env python3
"""Install pinned benchmark tools locally; does not change agent configuration."""

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import urllib.request
import zipfile

BASE = Path(__file__).resolve().parent
RELEASE = "https://github.com/dmtrKovalenko/fff/releases/download/v0.10.6/"


def main():
    if platform.system() != "Darwin" or platform.machine() != "arm64":
        raise SystemExit(
            "This pinned bundle targets macOS arm64. Select and verify the equivalent platform assets before running elsewhere."
        )
    metadata = {}
    for asset, dest in [
        ("fff-mcp-aarch64-apple-darwin", BASE / "fff/fff-mcp"),
        (
            "fff_search-0.10.6-cp310-abi3-macosx_11_0_arm64.whl",
            BASE / "fff/fff_search-0.10.6-cp310-abi3-macosx_11_0_arm64.whl",
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
        if actual != expected:
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
    binary_path = shutil.which("codebase-memory-mcp")
    if not binary_path:
        raise SystemExit("codebase-memory-mcp is required on PATH")
    binary = Path(binary_path)
    rg = shutil.which("rg")
    if not rg and (BASE / "tools.json").exists():
        rg = (
            json.loads((BASE / "tools.json").read_text()).get("ripgrep", {}).get("path")
        )
    if not rg:
        raise SystemExit("ripgrep is required")
    metadata["ripgrep"] = {
        "path": rg,
        "sha256": hashlib.sha256(Path(rg).read_bytes()).hexdigest(),
    }
    metadata["codebase-memory-mcp"] = {
        "path": str(binary),
        "sha256": hashlib.sha256(binary.read_bytes()).hexdigest(),
        "version": subprocess.check_output(
            [str(binary), "--version"], text=True
        ).strip(),
    }
    (BASE / "tools.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("Pinned tools ready; existing agent configuration was not changed.")


if __name__ == "__main__":
    main()
