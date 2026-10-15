"""Minimal SDK whitespace repro and cold-start corpus completeness checks."""

import json
from pathlib import Path
import sys
import subprocess
import tempfile
from agent_search_bench import BASE, Client


def fixture():
    sys.path.insert(0, str(BASE / "fff/sdk"))
    import fff

    with tempfile.TemporaryDirectory(prefix="fff-literal-repro-") as temp:
        root = Path(temp)
        corpus = root / "src"
        corpus.mkdir()
        (corpus / "sample.py").write_text(
            "import os\nimportThing = 1\ndef foo(): pass\ndefault = 1\n"
        )
        finder = fff.FileFinder(
            str(corpus),
            watch=False,
            frecency_db_path=str(root / "frecency"),
            history_db_path=str(root / "history"),
        )
        assert finder.wait_for_scan_blocking(60000)
        rows = []
        try:
            for query, mode in [
                ("import ", "plain"),
                ("def ", "plain"),
                (r"import\x20", "regex"),
                (r"def\x20", "regex"),
            ]:
                result = finder.grep(
                    query,
                    mode=mode,
                    smart_case=False,
                    max_matches_per_file=1000000,
                    page_limit=10000,
                )
                rows.append(
                    {
                        "query": query,
                        "mode": mode,
                        "lines": sorted(m.line_number for m in result.items),
                    }
                )
        finally:
            finder.close()
    assert rows[0]["lines"] == [1, 2], rows
    assert rows[1]["lines"] == [3, 4], rows
    assert rows[2]["lines"] == [1], rows
    assert rows[3]["lines"] == [3], rows
    return rows


def main():
    if "--fixture" in sys.argv:
        print(json.dumps(fixture()))
        return
    rows = json.loads(
        subprocess.check_output(
            [
                "/usr/bin/sandbox-exec",
                "-p",
                "(version 1)(allow default)(deny network*)",
                sys.executable,
                str(Path(__file__).resolve()),
                "--fixture",
            ],
            text=True,
        )
    )
    expected = next(
        len(q["expected"])
        for q in json.loads((BASE / "queries.json").read_text())
        if q["query"] == "import"
    )
    startup = []
    for trial in range(3):
        client = Client()
        try:
            counts = [
                client.act({"tool": "fff_search", "query": "import"})["result"]["total"]
                for _ in range(3)
            ]
            startup.append({"trial": trial, "counts": counts, "expected": expected})
        finally:
            client.close()
    output = {
        "whitespace_reproduced": True,
        "regex_preserves_space_on_fixture": True,
        "fixture": rows,
        "cold_start_trials": startup,
    }
    (BASE / "fff-sdk-edge-cases.json").write_text(json.dumps(output, indent=2) + "\n")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
