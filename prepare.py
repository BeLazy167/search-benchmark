#!/usr/bin/env python3
"""Freeze committed text from direct child repos; never run their code or hooks."""

import argparse
import hashlib
import json
import re
import subprocess
import tarfile
from collections import Counter
from pathlib import Path

BASE = Path(__file__).resolve().parent
EXTENSIONS = set(
    ".py .ts .tsx .js .jsx .mjs .cjs .go .rs .c .h .cpp .hpp .java .kt .swift .sh .bash .ps1 .sql .tf .md .mdx .rst .txt .json .yaml .yml .toml .ini .cfg .html .css .scss .graphql .proto .ipynb".split()
)
EXCLUDE_PARTS = {
    "node_modules",
    "vendor",
    "dist",
    "build",
    "coverage",
    "__pycache__",
    "venv",
    "target",
}
EXCLUDE_NAMES = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "bun.lock",
    "uv.lock",
    "Cargo.lock",
    "poetry.lock",
}


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def allowed(path):
    p = Path(path)
    return (
        not any(x.startswith(".") or x in EXCLUDE_PARTS for x in p.parts)
        and p.name not in EXCLUDE_NAMES
        and p.suffix.lower() in EXTENSIONS
        and not re.search(
            r"(^|[._-])(secret|credentials?|private[-_]?key|env)([._-]|$)", p.name, re.I
        )
    )


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=BASE.parents[1])
    parser.add_argument("--output", type=Path, default=BASE)
    parser.add_argument(
        "--manifest", type=Path, help="Rebuild precisely the recorded commits"
    )
    parser.add_argument("--exclude-paths", type=Path, help="Private JSON list of repository-relative paths to omit after review")
    args = parser.parse_args()
    excluded_paths = set(json.loads(args.exclude_paths.read_text())) if args.exclude_paths else set()
    if args.manifest:
        excluded_paths.update(json.loads(args.manifest.read_text()).get("policy", {}).get("review_excluded_paths", []))
    dest = args.output / "corpus"
    if dest.exists():
        raise SystemExit(
            f"Refusing to overwrite {dest}; choose a fresh --output directory"
        )
    dest.mkdir(parents=True)
    repos = []
    if args.manifest:
        repos = json.loads(args.manifest.read_text())["repositories"]
    else:
        for repo in sorted(args.root.iterdir()):
            if not repo.is_dir() or not (repo / ".git").exists():
                continue
            proc = subprocess.run(
                ["git", "-C", str(repo), "rev-parse", "--verify", "HEAD"],
                capture_output=True,
                text=True,
            )
            repos.append(
                {
                    "name": repo.name,
                    "commit": proc.stdout.strip() if proc.returncode == 0 else None,
                }
            )
    files, omissions, candidates = [], [], []
    for repo in repos:
        name, commit = repo["name"], repo["commit"]
        if commit is None:
            omissions.append({"repo": name, "reason": "no HEAD commit"})
            continue
        source = args.root / name
        p = subprocess.Popen(
            ["git", "-C", str(source), "archive", "--format=tar", commit],
            stdout=subprocess.PIPE,
        )
        counts = Counter()
        with tarfile.open(fileobj=p.stdout, mode="r|") as archive:
            for member in archive:
                if (
                    str(Path(name) / member.name) in excluded_paths
                    or not member.isfile()
                    or not allowed(member.name)
                    or member.size > 1024 * 1024
                ):
                    counts["excluded_path_type_or_size"] += 1
                    continue
                data = archive.extractfile(member).read()
                try:
                    content = data.decode("utf-8")
                except UnicodeDecodeError:
                    counts["non_utf8"] += 1
                    continue
                if b"\0" in data:
                    counts["binary"] += 1
                    continue
                path = Path(name) / member.name
                out = dest / path
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(data)
                files.append(
                    {
                        "path": path.as_posix(),
                        "bytes": len(data),
                        "sha256": hashlib.sha256(data).hexdigest(),
                    }
                )
                counts["included_files"] += 1
                counts["included_bytes"] += len(data)
                # Candidate locations are independently recognized, not tool rankings.
                for i, line in enumerate(content.split("\n"), 1):
                    match = re.match(
                        r"^(?:export\s+)?(?:async\s+)?(?:function|class|def|fn)\s+([A-Za-z_][A-Za-z_0-9]{7,})\b",
                        line,
                    )
                    if match and not match[1].startswith("test"):
                        candidates.append(
                            {
                                "repo": name,
                                "query": match[1],
                                "path": path.as_posix(),
                                "line": i,
                            }
                        )
        if p.wait() != 0:
            raise RuntimeError(f"git archive failed: {name}")
        repo["counts"] = dict(counts)
        print(name, counts["included_files"], flush=True)
    files.sort(key=lambda x: x["path"])
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    manifest = {
        "schema": 1,
        "repositories": repos,
        "files": files,
        "corpus_sha256": digest,
        "omissions": omissions,
        "policy": {
            "review_excluded_paths": sorted(excluded_paths),
            "max_file_bytes": 1048576,
            "extensions": sorted(EXTENSIONS),
            "excluded_parts": sorted(EXCLUDE_PARTS),
            "excluded_names": sorted(EXCLUDE_NAMES),
            "hidden_paths": "excluded",
            "symlinks_and_submodules": "excluded",
            "source": "git archive pinned HEAD; no dirty/untracked files",
        },
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    # One deterministic symbol per repo, with unique definition names preferred.
    frequencies = Counter(c["query"] for c in candidates)
    picked = []
    for repo in repos:
        choices = [c for c in candidates if c["repo"] == repo["name"]]
        choices.sort(
            key=lambda c: (
                frequencies[c["query"]] != 1,
                hashlib.sha256((c["path"] + c["query"]).encode()).hexdigest(),
            )
        )
        if choices:
            picked.append(choices[0])
    terms = list(
        dict.fromkeys(
            [c["query"] for c in picked]
            + [
                "import",
                "TODO",
                "organizationId",
                "getSession",
                "QBRAID_BENCH_NO_MATCH_8e9ab72",
            ]
        )
    )
    queries = [
        {"id": f"literal-{i:02d}", "query": term, "kind": "literal", "expected": []}
        for i, term in enumerate(terms)
    ]
    for entry in files:
        data = (dest / entry["path"]).read_bytes()
        for q in queries:
            needle = q["query"].encode()
            if needle in data:
                for line, value in enumerate(data.split(b"\n"), 1):
                    if needle in value:
                        q["expected"].append({"path": entry["path"], "line": line})
    (args.output / "queries.json").write_text(json.dumps(queries, indent=2) + "\n")
    (args.output / "symbols.json").write_text(json.dumps(picked, indent=2) + "\n")
    print(
        json.dumps(
            {
                "files": len(files),
                "bytes": sum(f["bytes"] for f in files),
                "queries": len(queries),
                "symbols": len(picked),
                "sha256": digest,
            }
        )
    )


if __name__ == "__main__":
    main()
