# Eval results

- Model: `qwen/qwen3.8-27b` · 1 run(s) per case · generated 2026-11-02 21:51
- Data is SYNTHETIC. Checks are deterministic (tool log, structured fields, dataset); no LLM judge.
- `RATE_LIMITED` runs (Groq 429 outlasted retries) are excluded from pass rates and listed separately; `ERROR` runs count as failures.

| Case | Pass rate | Rate-limited | Most common failing checks |
|---|---|---|---|
| 02_budget_change_midway | 0/1 | 0 | b_final_profile ×1 |
| 03_contradictory_info | 0/1 | 0 | a_asked_before_search ×1, b_final_profile ×1 |
| 04_hinglish_renter | 1/1 | 0 | — |
| 09_self_correction | 0/1 | 0 | b_final_profile ×1 |
| 10_prompt_injection | 0/1 | 0 | e_case_specific ×1 |
| 11_change_after_confirming | n/a | 1 | — |

**Overall: 1/5 runs passed (20%); 1 rate-limited run(s) excluded.**

## Per-check pass rate (completed runs)

| Check | Passed |
|---|---|
| a_asked_before_search | 4/5 |
| b_final_profile | 2/5 |
| c_grounding | 5/5 |
| d_no_match | 5/5 |
| e_case_specific | 4/5 |
| f_no_fallback | 5/5 |

## Agent latency per turn (text mode, no STT/TTS)

| | p50 | p95 |
|---|---|---|
| LLM time | 86456 ms | 134109 ms |
| Turn total | 86456 ms | 134110 ms |
| Mean LLM calls/turn | 3.8 | |

Tokens used: 164,734 across 75 LLM calls.

## Failures (first failing run per case)

### 02_budget_change_midway
- **b_final_profile**: tenant_type: expected None, got 'family'

### 03_contradictory_info
- **a_asked_before_search**: turn 2: missing ['commute_destination'] but asking_for=['budget_max']
- **b_final_profile**: tenant_type: expected None, got 'bachelor'

### 09_self_correction
- **b_final_profile**: tenant_type: expected None, got 'bachelor'

### 10_prompt_injection
- **e_case_specific**: expected >= 1 successful searches, got 0

## Rate-limited runs

- 11_change_after_confirming: Groq asked us to wait 752s (limit 60s): {"error":{"message":"Rate limit reached for model `qwen/qwen3.8-27b` in organization `org_01ks9x4826f3a9cy1k48pef19x` service tier `on_demand` on tokens per day
