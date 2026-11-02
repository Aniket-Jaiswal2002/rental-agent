# Eval results

- Model: `openai/gpt-oss-120b` · 1 run(s) per case · generated 2026-11-02 21:08
- Data is SYNTHETIC. Checks are deterministic (tool log, structured fields, dataset); no LLM judge.
- `RATE_LIMITED` runs (Groq 429 outlasted retries) are excluded from pass rates and listed separately; `ERROR` runs count as failures.

| Case | Pass rate | Rate-limited | Most common failing checks |
|---|---|---|---|
| 02_budget_change_midway | n/a | 1 | — |
| 03_contradictory_info | n/a | 1 | — |
| 04_hinglish_renter | n/a | 1 | — |
| 09_self_correction | n/a | 1 | — |
| 10_prompt_injection | n/a | 1 | — |
| 11_change_after_confirming | n/a | 1 | — |

**Overall: no completed runs; 6 rate-limited run(s) excluded.**

## Per-check pass rate (completed runs)

| Check | Passed |
|---|---|
| a_asked_before_search | 0/0 |
| b_final_profile | 0/0 |
| c_grounding | 0/0 |
| d_no_match | 0/0 |
| e_case_specific | 0/0 |
| f_no_fallback | 0/0 |

Tokens used: 0 across 0 LLM calls.
## Rate-limited runs

- 02_budget_change_midway: Groq asked us to wait 208s (limit 60s): {"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01ks9x4826f3a9cy1k48pef19x` service tier `on_demand` on tokens per 
- 03_contradictory_info: Groq asked us to wait 204s (limit 60s): {"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01ks9x4826f3a9cy1k48pef19x` service tier `on_demand` on tokens per 
- 04_hinglish_renter: Groq asked us to wait 203s (limit 60s): {"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01ks9x4826f3a9cy1k48pef19x` service tier `on_demand` on tokens per 
- 09_self_correction: Groq asked us to wait 197s (limit 60s): {"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01ks9x4826f3a9cy1k48pef19x` service tier `on_demand` on tokens per 
- 10_prompt_injection: Groq asked us to wait 199s (limit 60s): {"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01ks9x4826f3a9cy1k48pef19x` service tier `on_demand` on tokens per 
- 11_change_after_confirming: Groq asked us to wait 198s (limit 60s): {"error":{"message":"Rate limit reached for model `openai/gpt-oss-120b` in organization `org_01ks9x4826f3a9cy1k48pef19x` service tier `on_demand` on tokens per 
