> Historical notes from the September 2026 private-corpus experiment. Referenced raw artifacts and source files are not included in this public repository. These results have not been rerun for this release. Use the [current README](../README.md) for setup and portability limits.

> Follow-up: [multi-turn agents using the fff SDK](AGENT-SEARCH.md) completed 26 trials before model quota exhaustion and found SDK whitespace and cold-start edge cases beyond this original warmed benchmark.

# qBraid search-tool benchmark

Recommendation: keep codebase-memory-mcp for relationships and ripgrep for exhaustive text checks. fff is worth an optional trial for repeated discovery. This experiment does not establish a need to add Graphify alongside the existing codebase graph.

Corpus: 11,488 files, 89,970,642 bytes, 29 committed top-level repositories. `qbraid-review-harness` has no HEAD and is excluded. Exact commits, file hashes, exclusions, and per-repo coverage are saved in `manifest.json` and `repository-coverage.csv`.

## Exact text retrieval

31 case-sensitive fixed-string queries: one deterministic anchor from each eligible repo plus broad and absent terms. The independent oracle counts matching path/line pairs. The table excludes warm-up. No OS caches were purged.

| Tool/interface | Median ms | P95 ms | Exact query sets | Repetitions |
|---|---:|---:|---:|---:|
| ripgrep | 140.5 | 267.0 | 31/31 | 7 |
| grep | 916.5 | 1306.5 | 31/31 | 7 |
| fff-sdk | 41.5 | 413.0 | 31/31 | 7 |
| fff-mcp | 65.0 | 1426.4 | 24/31 | 3 |

fff SDK directory-scan/startup measurement: 0.153s. The first full workload pass is warm-up and may absorb remaining content-index work. This is not comparable to a completed structural graph build.

SDK calls retain the index in-process. CLI results include process startup, capture, and normalization. fff MCP uses persistent stdio, requests up to one million results, and follows every returned cursor. It still caps matches per file and uses smart-case/fuzzy behavior. Its faster incomplete output is not an exact-search speed win. The SDK was explicitly configured for case-sensitive plain search and complete pagination.

fff filename typo smoke test: 6/6 target files appeared in the first 10 results. These are six constructed typos, not a broad relevance benchmark. Git-history ranking is not evaluated because the archive corpus has no Git metadata.

## Structural indexing and retrieval

| Tool | Initial graph build | Correct direct caller sets |
|---|---:|---:|
| codebase-memory-mcp 0.8.1, full, LSP disabled | 16.21s | 12/12 |
| Graphify 0.9.56, code-only, no clustering, HCL parser installed | 106.70s | 12/12 |

Graphify unchanged cached extraction: 23.06s. The initial default installation skipped 290 Terraform files; the reported build uses its optional HCL parser. Four syntax-error warnings remain in existing TSX input; these are parser reports, not diagnosed application defects.

Caller truth comes from Python AST parsing of direct calls between top-level functions in the same file, with nested scopes excluded. It is a small, deliberately checkable suite across six repos. No claim is made about dynamic dispatch, cross-file alias resolution, language-server quality, or cross-repo HTTP contracts.

| Warm query interface | Symbol median ms | Caller median ms |
|---|---:|---:|
| codebase-memory | 23.48 | 24.52 |
| graphify-query | 743.01 | 988.04 |

Codebase timings include persistent MCP and JSON handling; caller work includes symbol resolution plus trace_path. Graphify timings call its pinned MCP query function in-process, with graph load excluded, depth 2, and requested token budget 2,000. These are different query operations. Graphify exact-node `explain` is evaluated separately below, including resolving the target by its supplied symbol/file.

## Fixed-evidence model pilot

Model: `gpt-5.3-codex-spark` through the user-selected CLIProxy, low reasoning effort requested. Six same-file caller questions, two repetitions, identical prompts, randomized order. The model sees no tool name or gold answer. Evidence is capped at 12,000 UTF-8 bytes for every tool. Responses are graded by exact caller-name sets, not an LLM judge.

| Evidence configuration | Exact answers | Input tokens | Output tokens incl. reasoning |
|---|---:|---:|---:|
| codebase | 12/12 | 12,544 | 1,148 |
| fff-mcp | 6/12 | 14,186 | 2,599 |
| fff-usage | 6/12 | 14,186 | 2,386 |
| graphify | 4/12 | 26,154 | 4,756 |
| graphify-explain | 12/12 | 4,882 | 1,327 |
| grep | 10/12 | 30,836 | 3,081 |
| ripgrep | 10/12 | 30,836 | 2,705 |

The targeted Graphify result matters: its graph contains the answers, while broad natural-language query scoring can bury them. The exact-node explain configuration matches codebase on this pilot. fff content and usage output both miss caller evidence in this fixed bundle; a real agent could recover by reading the file. Grep and ripgrep use 40 preceding and 5 following context lines on the supplied file. This pilot has no follow-up read, autonomous tool choice, or code changes, so it is not a productivity leaderboard.

The targeted Graphify and fff usage checks were added after observing the broad-query results. They are disclosed as follow-up configurations, not a preregistered competition. Graphify resolves only the target symbol/file, never the expected callers. Raw requests, answers, token breakdowns, and grading are in `qa-results.jsonl`. Luna quota failures and the unavailable plain gpt-5.3-codex alias are also recorded; no successful Luna run is claimed.

## Reproduction and limits

See `README.md` for commands, `RESEARCH.md` for primary-source benchmark inspiration, and `verify.py` for integrity and correctness checks. Timings will vary with machine load. Pinned corpus hashes and correctness outcomes should reproduce on this configuration. SDK/native binaries are pinned for macOS arm64; the installed codebase binary SHA256 is recorded rather than silently replaced.

The first text run and the first codebase full index included a Graphify-generated cache file. They are retained under names containing `invalid-extra-cache` and excluded from the reported results. The final text run and codebase index use the verified clean corpus. Graphify excludes its own output directory; its graph was checked to contain no sidecar source nodes. The rerun configuration explicitly routes Graphify output outside the corpus.

All local parsing/search runs deny network. No application server, database mutation, primary-checkout edit, push, or publishing was performed. The corpus excludes dirty/untracked files, hidden paths, symlinks, submodule contents, listed generated/dependency directories, common lockfiles and credential/environment filenames, binary/non-UTF8 data, and files larger than 1 MiB. Coverage therefore means this documented text corpus, not every byte on disk.
