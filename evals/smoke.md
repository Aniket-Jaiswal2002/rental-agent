# Eval results

- Model: `openai/gpt-oss-120b` · 1 run(s) per case · generated 2026-11-02 20:46
- Data is SYNTHETIC. Checks are deterministic (tool log, structured fields, dataset); no LLM judge.
- `RATE_LIMITED` runs (Groq 429 outlasted retries) are excluded from pass rates and listed separately; `ERROR` runs count as failures.

| Case | Pass rate | Rate-limited | Most common failing checks |
|---|---|---|---|
| 07_everything_in_one_sentence | 1/1 | 0 | — |

**Overall: 1/1 runs passed (100%); 0 rate-limited run(s) excluded.**

## Per-check pass rate (completed runs)

| Check | Passed |
|---|---|
| a_asked_before_search | 1/1 |
| b_final_profile | 1/1 |
| c_grounding | 1/1 |
| d_no_match | 1/1 |
| e_case_specific | 1/1 |
| f_no_fallback | 1/1 |

## Agent latency per turn (text mode, no STT/TTS)

| | p50 | p95 |
|---|---|---|
| LLM time | 15880 ms | 33208 ms |
| Turn total | 15881 ms | 33209 ms |
| Mean LLM calls/turn | 3.0 | |

Tokens used: 12,128 across 6 LLM calls.
