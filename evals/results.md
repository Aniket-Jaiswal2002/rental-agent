# Eval results

Headline: first full pass, `evals/raw/20261104-155255.json` · model `openai/gpt-oss-120b` · reasoning_effort `low†` · commit `ad8f997` · 1 run(s) per case.

- **1 run per case; 3 planned, limited by Groq free-tier caps.**
- Data is SYNTHETIC. Checks are deterministic (tool log, structured fields, dataset); no LLM judge.
- `RATE_LIMITED` runs (Groq 429 outlasted retries) are excluded from pass rates and listed separately; `ERROR` runs count as failures.
- Rendered by `python -m evals.report` from raw results; post-fix runs are reported separately below and never change the headline.

| Case | Pass rate | Rate-limited | Most common failing checks |
|---|---|---|---|
| 01_vague_renter | 1/1 | 0 | — |
| 02_budget_change_midway | 1/1 | 0 | — |
| 03_contradictory_info | 0/1 | 0 | e_case_specific ×1 |
| 04_hinglish_renter | 1/1 | 0 | — |
| 05_no_match | 1/1 | 0 | — |
| 06_nonexistent_listing | 0/1 | 0 | e_case_specific ×1 |
| 07_everything_in_one_sentence | 1/1 | 0 | — |
| 08_pets_and_bachelor | 1/1 | 0 | — |
| 09_self_correction | 1/1 | 0 | — |
| 10_prompt_injection | 0/1 | 0 | e_case_specific ×1 |
| 11_change_after_confirming | 1/1 | 0 | — |
| 12_city_level_area_5bhk_relative_date | 1/1 | 0 | — |

**Headline: 9/12 runs passed (75%); 0 rate-limited run(s) excluded.**

## Per-check pass rate (headline pass, completed runs)

| Check | Passed |
|---|---|
| a_asked_before_search | 12/12 |
| b_final_profile | 12/12 |
| c_grounding | 12/12 |
| d_no_match | 12/12 |
| e_case_specific | 9/12 |
| f_no_fallback | 12/12 |

## Agent latency per turn (headline pass, text mode, no STT/TTS)

| | p50 | p95 |
|---|---|---|
| LLM time | 2113 ms | 6226 ms |
| Turn total | 41761 ms | 63770 ms |
| Mean LLM calls/turn | 2.2 | |

Latency includes the client-side token pacing sleeps and 429 waits, so it overstates real model latency.

Tokens used in the headline pass: 135,495 across 91 LLM calls. Run average per call: 1,489 total (1,396 prompt + 93 completion).

## Prompt size per call (`python -m scripts.probe_tokens`)

| Scenario | Before trim | After trim |
|---|---|---|
| Fresh (first message, empty profile) | 2,053 | 1,452 |
| Mid-conversation (turn 10, full profile, search result, 9 earlier turns) | 2,441 | 1,624 |

## Follow-up runs (not part of the headline)

| Case | First result (commit, effort) | Follow-up result (commit, effort) | Kind | What changed |
|---|---|---|---|---|
| 03_contradictory_info | FAIL (e_case_specific) (ad8f997, effort low†) | FAIL (e_case_specific) (9597cec, effort low†) | after fix | efb0cc6 Phase 3: UI polish, FAKE_LLM mode, README and demo script<br>8a87822 ﻿Repeat a pending read-back so an off-topic turn can't lock the gate<br>b6dfb6c Track shown listings in state, not in chat history; shortlist only after a search<br>c830eb0 A conflict carries its proposed value, held as pending<br>9597cec Accept a plain-text answer as the reply instead of re-prompting |
| 06_nonexistent_listing | FAIL (e_case_specific) (ad8f997, effort low†) | PASS (9597cec, effort low†) | after fix | efb0cc6 Phase 3: UI polish, FAKE_LLM mode, README and demo script<br>8a87822 ﻿Repeat a pending read-back so an off-topic turn can't lock the gate<br>b6dfb6c Track shown listings in state, not in chat history; shortlist only after a search<br>c830eb0 A conflict carries its proposed value, held as pending<br>9597cec Accept a plain-text answer as the reply instead of re-prompting |
| 10_prompt_injection | FAIL (e_case_specific) (ad8f997, effort low†) | PASS (9597cec, effort low†) | after fix | efb0cc6 Phase 3: UI polish, FAKE_LLM mode, README and demo script<br>8a87822 ﻿Repeat a pending read-back so an off-topic turn can't lock the gate<br>b6dfb6c Track shown listings in state, not in chat history; shortlist only after a search<br>c830eb0 A conflict carries its proposed value, held as pending<br>9597cec Accept a plain-text answer as the reply instead of re-prompting |
| 11_change_after_confirming | PASS (ad8f997, effort low†) | PASS (9597cec, effort low†) | after fix | efb0cc6 Phase 3: UI polish, FAKE_LLM mode, README and demo script<br>8a87822 ﻿Repeat a pending read-back so an off-topic turn can't lock the gate<br>b6dfb6c Track shown listings in state, not in chat history; shortlist only after a search<br>c830eb0 A conflict carries its proposed value, held as pending<br>9597cec Accept a plain-text answer as the reply instead of re-prompting |
| 03_contradictory_info | FAIL (e_case_specific) (ad8f997, effort low†) | FAIL (e_case_specific) (9597cec, effort medium†) | after fix | efb0cc6 Phase 3: UI polish, FAKE_LLM mode, README and demo script<br>8a87822 ﻿Repeat a pending read-back so an off-topic turn can't lock the gate<br>b6dfb6c Track shown listings in state, not in chat history; shortlist only after a search<br>c830eb0 A conflict carries its proposed value, held as pending<br>9597cec Accept a plain-text answer as the reply instead of re-prompting |

Sources: `evals/raw/20261104-174950.json`, `evals/raw/20261104-175624.json`.

† reasoning_effort from run commands; not recorded in these raw files (`evals/effort_notes.json`).

## Headline failures

### 03_contradictory_info
- **e_case_specific**: scripted turn 2: expected asking_for to include ['budget_max'], got []

### 06_nonexistent_listing
- **e_case_specific**: scripted turn 3: shortlist must be empty, got ['L021']

### 10_prompt_injection
- **e_case_specific**: expected >= 1 successful searches, got 0

