> Historical notes from the September 2026 private-corpus experiment. Referenced raw artifacts and source files are not included in this public repository. These results have not been rerun for this release. Use the [current README](../README.md) for setup and portability limits.

# Agents using fff SDK and ripgrep

This follow-up tests multi-turn model-driven retrieval, rather than giving the model fixed evidence. It uses gpt-5.3-codex-spark through the user-selected local CLIProxy endpoint, with low reasoning effort.

The planned workload runs the 12 existing independently graded caller tasks once per configuration: fff SDK only, ripgrep only, and agent choice of both. Each task starts with only a repository and target function name. The agent chooses search queries, optional path prefixes, pagination, source reads, and when to answer. The final target file and direct same-file top-level caller set must both match the Python AST oracle. The oracle is never included in model messages.

The agent uses provider-native function calls with parallel calls disabled in the request; if the provider still returns multiple calls, the harness executes them sequentially. A native-protocol pilot exposed this provider behavior and is retained separately in `agent-search-native-protocol-pilot.jsonl`, excluded from results. An initial JSON chat protocol pilot produced malformed multi-action responses; it is retained separately in `agent-search-json-protocol-pilot.jsonl` and excluded from the comparison. It has up to 12 model turns per task. Search tools return the same sorted, paginated format (100 exact line matches per page). Reads return up to 200 lines. Both tools search the same pinned corpus by default. The interface promises exact matching, but the follow-up replay below found SDK semantic and snippet differences; this promise is not yet fully implemented. fff uses its persistent Python SDK directly with its full-result configuration, bypassing MCP caps. The wrapper consumes native pages before presenting normalized pages. ripgrep starts a process for each search. File reads and retrieval execute in a network-denied child process; only the parent makes model requests.

Task/configuration order is shuffled with seed 921. In the choice configuration, search-tool listing order is counterbalanced by task ID. Tool descriptions promise identical exact-match behavior and make no speed claims. Source output is untrusted data. Agent access is confined to the committed benchmark corpus; no arbitrary shell execution is exposed.

The backend scan/startup time is recorded separately from each agent task. End-to-end task time includes model calls, searches and reads. No OS cache purge or cache billing adjustment is attempted. The choice configuration shares the same persistent backend. This is a small constrained code-investigation evaluation, not a benchmark of autonomous code changes or real PR review, and does not test fff fuzzy ranking. One run per task/configuration cannot establish stable model preference or statistically reliable end-to-end speed differences.

Run from this directory:

```sh
graphify/.venv/bin/python agent_search_bench.py --smoke
graphify/.venv/bin/python agent_search_bench.py
graphify/.venv/bin/python agent_search_bench.py --summarize
```

The normal run resumes completed task/configuration pairs in `agent-search-results.jsonl`. To obtain a fresh repetition, first move that file to a distinct archival name. Raw results include initial prompts, each action, every tool result, model token usage, final answers, timings, and grading. `agent-search-summary.json` aggregates those traces. Running the model test makes API requests through CLIProxy; the smoke test is local only.

The initial smoke checks passed SDK/rg output equality for selected sparse and dense queries, including pagination and a query affected by the earlier MCP per-file cap. The broader agent-query replay subsequently found differences listed below. It also checks read limits and rejection of paths outside the corpus. Every model run verifies the complete corpus inventory and hashes before starting.

A paired replay (`agent_search_replay.py`) reruns each distinct agent-chosen search request against both engines, records normalized-output discrepancies, and measures one warm-up plus three shuffled repetitions. Run it after the agent loop finishes to avoid overlapping timed search workloads. `verify_agent_search.py` independently recomputes caller sets from source and checks trial grades, task/configuration coverage, allowed tools, and the paired replay artifact. Use `--allow-partial` for the quota-interrupted run; a passing audit explicitly reports incomplete coverage.

## Findings from the quota-interrupted run

The SDK wrapper is usable by an agent and provides fast repeated retrieval, but this test does not establish a safe replacement for ripgrep. The original statement that the SDK recovered all exact matches applied to the earlier warmed query set; it does not cover the new cold-start and whitespace cases.

26 of 36 planned agent trials completed; one further task stopped after two model turns with HTTP 429. A fresh retry confirmed `model_cooldown` / `usage_limit_reached`, with about 3h29m until reset at the time of the check. Ten task/configuration pairs remain incomplete. No model was substituted.

| Configuration | Exact completed answers | Median task time |
|---|---:|---:|
| fff SDK wrapper | 8/8 | 10.22 s |
| ripgrep wrapper | 7/9 | 9.58 s |
| Agent choice of either | 9/9 | 12.08 s |

These are different completed task subsets. On the five tasks completed in all three configurations, fff scored 5/5, rg 4/5, and choice 5/5; median task times were 10.19 s, 9.58 s, and 13.16 s respectively. This small unreplicated sample does not show an end-to-end speed advantage for fff. Model time dominates retrieval time.

Of nine choice trials, three used only fff search and six only rg search; none switched engines. This is observed selection under the supplied tool descriptions, not a reliable model preference estimate.

The rg errors have distinct causes: one returned the right caller names from a file in the wrong repository; another exhausted its turn limit after repeatedly using `.` as a literal path prefix. The latter is an adapter usability defect, not a ripgrep engine failure. The shared wrapper now normalizes `.` and `./` scopes and the local smoke regression passes. Model results were recorded before that correction; quota prevents the corrected model rerun.

A paired local replay of 48 distinct agent-chosen search requests measured a median 20.65 ms for fff and 153.38 ms for rg (one warm-up, three repetitions, 144 measured calls per engine). It used the corrected scope normalization. Forty-five requests had identical output; three differed consistently: `import ` and `def ` had different match counts because SDK plain mode trims surrounding whitespace; `validate` had matching path/line entries on the returned page but shorter line text from fff. These timings therefore are not proof of fully equivalent work. Raw mismatches are retained in `agent-search-replay.json`.

`fff_sdk_edge_cases.py` reproduces whitespace trimming on a four-line fixture: `import ` also matches `importThing`, and `def ` also matches `default`. Escaping spaces as `\x20` in regex mode preserves literal-space matching on that fixture, but this workaround has not been integrated or evaluated with the model.

Three fresh SDK processes on the full corpus each returned 40,590 matches for the first `import` query, then 46,941 for the next two calls. The independent oracle expects 46,941. Each process had already completed `wait_for_scan_blocking`. The observed symptom is reproducible; the native SDK root cause is not established. An arbitrary sleep or retry-until-stable workaround is not treated as a correctness guarantee.

The wrapper is an experimental benchmark tool, not a globally configured agent search replacement. Keep rg available until SDK readiness, literal whitespace semantics, and shortened snippets are handled and the corrected agent run completes.

Verification: 26 recorded grades and 12 source-derived oracles passed audit, with coverage explicitly incomplete; local wrapper smoke checks and four existing harness tests passed. Whitespace/cold-start repros successfully reproduce failures. A passing artifact audit does not mean all search outputs agree.

Additional commands:

```sh
graphify/.venv/bin/python agent_search_replay.py
graphify/.venv/bin/python fff_sdk_edge_cases.py
graphify/.venv/bin/python verify_agent_search.py --allow-partial
```

Preserve the current results before a clean model rerun because scope behavior has changed since these trials. Simply resuming would skip the completed scope-failure trial. The exact pre-correction harness is archived as `agent_search_bench_before_scope_fix.py` and matches its recorded hash in `agent-search-provenance.json`; current local correction hashes are in `agent-search-local-fixes.json`.
