# Search benchmark

Compare ripgrep, grep, fff, codebase-memory-mcp, and Graphify on the same committed source files. The scripts measure literal-search correctness and latency, graph indexing, and direct Python caller retrieval. Optional experiments measure model answers from search evidence and multi-turn search agents.

This repository contains the benchmark scripts from a September 2026 qBraid workspace experiment. It does **not** include the original source corpus, raw model conversations, generated indexes, or saved results. Build a corpus from repositories you can access. The MIT license covers these scripts, not the repositories you benchmark or the third-party tools.

Historical findings are in [the original report](docs/REPORT.md), [the agent follow-up](docs/AGENT-SEARCH.md), and [the methodology notes](docs/RESEARCH.md). They describe the private dataset, not results on your repositories.

## Requirements

The full tool setup targets **macOS on Apple Silicon**. Several runners use `/usr/bin/sandbox-exec` to deny network access to search processes. Linux and Windows need different release artifacts and an equivalent sandbox before those runners will work.

Install Git, Python 3.13, [uv](https://docs.astral.sh/uv/), [ripgrep](https://github.com/BurntSushi/ripgrep), and [codebase-memory-mcp](https://github.com/DeusData/codebase-memory-mcp). Put `rg` and `codebase-memory-mcp` on `PATH`.

`bootstrap.py` downloads fff 0.10.6 with checksum verification and installs Graphify at commit `67f99bd0059dd1bac9e44382907ef9f10098b39f` using `graphify/requirements.lock`. It records the installed codebase-memory-mcp binary's hash and version; it does not install or pin that binary. The original experiment used version 0.8.1. Newer versions may require changes to the graph runners' API calls. Version 0.11.0 also rejects this runner's isolated cache when an existing account daemon uses another cache. Use a separate environment with the compatible tool version; do not stop other active sessions to run a benchmark.

## Quick start

```sh
git clone https://github.com/BeLazy167/search-benchmark.git
cd search-benchmark
python3 bootstrap.py
```

Place the Git repositories to benchmark under one directory, for example:

```text
/path/to/repos/
  project-a/.git
  project-b/.git
```

Use a dedicated input directory. Each repository needs a commit. Preparation reads committed files with `git archive`; it does not run their code or include uncommitted changes.

```sh
graphify/.venv/bin/python prepare.py --root /path/to/repos
graphify/.venv/bin/python build_relationships.py
graphify/.venv/bin/python text_bench.py --smoke --repeats 1
```

The smoke run checks the first two literal queries. Run the full literal workload with:

```sh
graphify/.venv/bin/python text_bench.py --repeats 7
```

Results go to `text-results.json`. Each trial records elapsed milliseconds, exact-match status, false positives, false negatives, and output size. Trial `-1` is warm-up. The terminal prints median latency and exact-match counts for each tool.

`prepare.py` creates `corpus/`, `manifest.json`, `queries.json`, and `symbols.json`. It excludes hidden paths, common dependency/build directories, symlinks, submodules, common credential filenames, non-UTF-8 files, and files larger than 1 MiB. These filters are not a secret scanner. Keep generated outputs private unless you have reviewed their contents and have permission to publish the input code.

Preparation refuses to overwrite an existing corpus. Use a fresh clone for a different dataset. To reconstruct recorded commits in another output directory:

```sh
graphify/.venv/bin/python prepare.py \
  --root /path/to/repos \
  --manifest manifest.json \
  --output /tmp/search-benchmark-rebuilt
```

The source repositories must still contain the recorded commits; this command does not fetch them.

## Additional reusable benchmarks

Run these after preparation and tool setup:

```sh
# fff's persistent MCP interface, including pagination
graphify/.venv/bin/python fff_mcp_bench.py --repeats 3

# AST graph indexing and symbol/caller queries
graphify/.venv/bin/python codebase_bench.py --repeats 7

# Graphify indexing, then queries against the saved graph
graphify/.venv/bin/python graphify/run.py --output graphify/run-hcl
graphify/.venv/bin/python graph_queries.py --repeats 7
```

Graphify needs a fresh output directory for an initial index. Pass `--skip-index` to its runner to reuse an existing graph. The caller oracle selects up to 12 examples, with at most two per input repository. A corpus without suitable Python functions can produce no caller tasks.

## Experimental and dataset-specific scripts

The remaining scripts preserve the original research workflow. They are starting points for adaptation, not a portable one-command benchmark:

| Scripts | What needs adapting |
| --- | --- |
| `fuzzy_bench.py` | The six typo queries and target paths refer to the original qBraid corpus. |
| `run_all.py` | Calls the dataset-specific fuzzy benchmark; use the individual runners above for a new dataset. |
| `qa_pilot.py`, `prepare_qa_evidence.py`, `targeted_evidence.py` | The model pilot selects specific caller task IDs. Choose IDs present in your generated `relationships.json`. |
| `agent_search_bench.py` | Its smoke check includes an original corpus path; its ripgrep subprocess expects `/opt/homebrew/bin/rg`. |
| `proxy_client.py`, `luna.py` | Expect a local CLIProxy endpoint and configuration at `~/.cli-proxy-api/config.yaml`. Review the model and endpoint before use. |
| `summarize.py`, `verify.py` | Expect a complete set of original experiment artifacts and include original dataset assumptions. |
| `agent_search_replay.py`, `verify_agent_search.py` | Require saved agent trials; they cannot validate absent historical results. |
| `agent_search_bench_before_scope_fix.py` | Historical version retained for comparison; use `agent_search_bench.py` for new work. |

Model experiments send source excerpts to the configured provider and may incur charges. The quick start makes no model requests. Raw model outputs and graph evidence can contain input source code.

## Interpreting results

Compare correctness before latency. fff MCP's smart-case/fuzzy behavior and per-file match limits differ from exact grep. The SDK runner explicitly requests case-sensitive plain matches and consumes pagination.

Timing boundaries differ: grep and ripgrep include process startup and output parsing, while the fff SDK keeps an in-process index. Graphify query timing excludes graph loading and MCP transport. Index-build times are separate from query times. Warm runs do not represent cold disk access.

The caller oracle only covers direct named calls between top-level Python functions in the same file. It excludes nested scopes and does not resolve imports, aliases, callbacks, or dynamic dispatch. Small model experiments do not establish general coding productivity.

## Release verification

A clean bootstrap, all four unit tests, a two-query literal smoke run, fff MCP, and Graphify indexing/querying passed on a small committed Python sample on macOS arm64. The codebase-memory runner was blocked by the installed 0.11.0 daemon/cache restriction described above. Model requests and the full private-corpus experiment were not rerun.

## Development

After bootstrap, run the existing unit checks:

```sh
graphify/.venv/bin/python -m unittest test_harness.py
```

Changes to a runner should include a small corpus check and state the tool versions used. Open an issue or pull request with the command, platform, versions, and a minimal public sample. Do not attach private source or credentials.

## License

[MIT](LICENSE). Third-party tools retain their own licenses and are downloaded separately.
