> Historical notes from the September 2026 private-corpus experiment. Referenced raw artifacts and source files are not included in this public repository. These results have not been rerun for this release. Use the [current README](../README.md) for setup and portability limits.

# Benchmark research

Sources checked on 2026-09-08. These are first-party methods, not independent proof of the authors' speed or accuracy claims.

| Source | Useful design choice | Applied here |
|---|---|---|
| [ripgrep author Andrew Gallant's comparison](https://burntsushi.net/ripgrep/) | Checks matched-line counts, varies workload, distinguishes file selection and output work from matching. | One immutable text corpus; independent expected path/line sets; case-sensitive ASCII literals; output captured rather than discarded; rare, common, and absent queries. |
| [fff's Criterion grep benchmark](https://github.com/dmtrKovalenko/fff/blob/v0.10.6/crates/fff-core/benches/grep_bench.rs) | Separates dense-match and no-match cases, makes pagination non-limiting, and tests a persistent picker. | Explicit SDK pagination and match limits; scan time separate from repeated searches; SDK and MCP reported separately. |
| [fff's Claude benchmark script](https://github.com/dmtrKovalenko/fff/blob/main/scripts/benchmark-claude.sh) | Runs the same coding model with fff or native search; records tokens, turns, cost, and target-file success. | A fixed-model evidence-reading pilot with identical prompts and an automatic answer oracle; actual token usage recorded. We do not reuse its developer-specific corpus path or authentication setup. |
| [Graphify benchmark documentation](https://github.com/Graphify-Labs/graphify/blob/67f99bd0059dd1bac9e44382907ef9f10098b39f/BENCHMARKS.md) | Separates ingest, retrieval, answer, and grading; holds the model/budget constant. Its code-intelligence result uses six ERPNext questions. | Separate indexing, retrieval, and model-answer results. Our six-question pilot is also small and is not a broad claim about coding productivity. Its LOCOMO conversational-memory scores are not code-search scores. |
| [Graphify AST extraction benchmark](https://github.com/Graphify-Labs/graphify/blob/67f99bd0059dd1bac9e44382907ef9f10098b39f/tests/bench_extract.py) | Clears AST caches when comparing extraction, and checks sequential/parallel output equality. | Fresh output directory for initial extraction; cached unchanged extraction shown separately; four configured extraction workers. |
| [Codebase-Memory preprint](https://arxiv.org/abs/2603.27277) | Evaluates structured graph exploration against file-oriented exploration. | Structural caller tasks get their own oracle and metric; graph search is not treated as a complete literal grep replacement. |

Important limits of this experiment:

- Timings come from a shared macOS workstation. Timed local search/index workloads run sequentially, but unrelated user processes remain running. Model API requests overlapped the final text run; their latency is not used to rank local search speed. No privileged OS cache purge was performed. “Initial” means first index creation in a fresh tool directory, not a cold disk.
- All tools receive the same pinned source corpus, but their language support and internal exclusion rules differ. Node counts are not comparable measures of accuracy.
- fff SDK runs in the Python process; grep/ripgrep include process launch, capture, and normalization. Codebase uses persistent stdio MCP. Graphify uses its pinned MCP query implementation in-process, excluding transport. These boundaries are explicit, not equivalent CPU microbenchmarks.
- The caller oracle covers direct named calls between top-level Python functions within the same file. It does not prove correctness for polymorphism, alias resolution, callbacks, imports, dynamic dispatch, or cross-service edges.
- The model pilot reads a fixed evidence bundle. It does not choose tools, recover through multiple searches, edit code, or run tests. Tools are hidden from the model and gold answers are never included in its prompt.
- The requested Luna model was quota-blocked. The user authorized 5.3 Codex next; the working proxy model is `gpt-5.3-codex-spark`, with low reasoning effort requested consistently in the pilot.
