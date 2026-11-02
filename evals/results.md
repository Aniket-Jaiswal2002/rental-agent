# Eval results

- Model: `openai/gpt-oss-120b` · 1 run(s) per case · generated 2026-11-02 21:06
- Data is SYNTHETIC. Checks are deterministic (tool log, structured fields, dataset); no LLM judge.
- `RATE_LIMITED` runs (Groq 429 outlasted retries) are excluded from pass rates and listed separately; `ERROR` runs count as failures.

| Case | Pass rate | Rate-limited | Most common failing checks |
|---|---|---|---|
| 01_vague_renter | 1/1 | 0 | — |
| 02_budget_change_midway | 0/1 | 0 | a_asked_before_search ×1, f_no_fallback ×1 |
| 03_contradictory_info | 0/1 | 0 | e_case_specific ×1 |
| 04_hinglish_renter | 0/1 | 0 | a_asked_before_search ×1, f_no_fallback ×1 |
| 05_no_match | 1/1 | 0 | — |
| 06_nonexistent_listing | 1/1 | 0 | — |
| 07_everything_in_one_sentence | 1/1 | 0 | — |
| 08_pets_and_bachelor | 1/1 | 0 | — |
| 09_self_correction | n/a | 1 | — |
| 10_prompt_injection | n/a | 1 | — |
| 11_change_after_confirming | n/a | 1 | — |

**Overall: 5/8 runs passed (62%); 3 rate-limited run(s) excluded.**

## Per-check pass rate (completed runs)

| Check | Passed |
|---|---|
| a_asked_before_search | 6/8 |
| b_final_profile | 8/8 |
| c_grounding | 8/8 |
| d_no_match | 8/8 |
| e_case_specific | 7/8 |
| f_no_fallback | 6/8 |

## Agent latency per turn (text mode, no STT/TTS)

| | p50 | p95 |
|---|---|---|
| LLM time | 35699 ms | 129616 ms |
| Turn total | 35700 ms | 129616 ms |
| Mean LLM calls/turn | 3.5 | |

Tokens used: 136,930 across 100 LLM calls.

## Failures (first failing run per case)

### 02_budget_change_midway
- **a_asked_before_search**: turn 1: missing ['commute_destination', 'move_in_date'] but asking_for=[]
- **f_no_fallback**: turn 1: fallback reply (no valid respond)

### 03_contradictory_info
- **e_case_specific**: scripted turn 2: expected asking_for to include ['budget_max'], got []

### 04_hinglish_renter
- **a_asked_before_search**: turn 1: missing ['areas', 'commute_destination', 'move_in_date'] but asking_for=[]
- **f_no_fallback**: turn 1: fallback reply (no valid respond)

## Rate-limited runs

- 09_self_correction: Groq asked us to wait 474s (limit 60s): {"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01ks9x4826f3a9cy1k48pef19x` service tier `on_demand` on tokens per 
- 10_prompt_injection: Groq asked us to wait 247s (limit 60s): {"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01ks9x4826f3a9cy1k48pef19x` service tier `on_demand` on tokens per 
- 11_change_after_confirming: Groq asked us to wait 246s (limit 60s): {"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01ks9x4826f3a9cy1k48pef19x` service tier `on_demand` on tokens per 
