# Voice renter-intake agent (demo)

A voice-first agent that takes a renter from "I need a home" to a confirmed search profile and a grounded
top-3 shortlist of Gurugram rentals. All listing data is **SYNTHETIC** (`data/listings.json`).

> Work in progress. The full README (architecture, eval table, latency numbers, limitations, next steps) comes in Phase 3.

## Run

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements.txt
copy .env.example .env   # then add GROQ_API_KEY
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m app.cli                      # text chat
.venv\Scripts\uvicorn app.server:app --port 8000     # voice UI at http://localhost:8000
```

Evals (one pass, resumable across Groq quota windows):

```bash
.venv\Scripts\python -m evals.run                    # stops cleanly if the quota runs out
.venv\Scripts\python -m evals.run --resume           # next window: finishes the remaining cases
.venv\Scripts\python -m evals.report evals/raw/<pass>.json
```

## Design decisions

- **Search uses the confirmed profile.** `search_listings` takes no model-supplied filters; it reads the profile
  the renter confirmed, so the model cannot drift from what was agreed.
- **Eval check (a) counts volunteered fields as handled.** A required field the renter volunteers without being
  asked does not fail "asked before searching"; the check fails only if a missing field was never asked about
  and the renter did not supply it on the next turn.

## Built on free-tier limits

The whole demo runs on Groq's free tier (`openai/gpt-oss-120b`: about 8K tokens/minute and a daily token cap).
That shaped a few choices:

- **Token pacing.** The Groq client sleeps *before* a request if it would push the last 60 seconds over
  `GROQ_TPM` (7,000) tokens, instead of retrying into 429s. Real 429s are retried with exponential backoff
  and honour `retry-after` up to `GROQ_MAX_WAIT_S`.
- **Prompt trim.** Shorter system prompt and tool schemas. Prompt tokens per call, measured with
  `python -m scripts.probe_tokens` (Groq's own usage numbers):

  | Scenario | Before | After |
  |---|---|---|
  | Fresh (first message, empty profile) | 2,053 | 1,452 |
  | Mid-conversation (turn 10, full profile, search result, 9 earlier turns) | 2,441 | 1,624 |

- **Last-3-turn history, profile as memory.** Only the last 3 renter/assistant exchanges are resent. Everything
  older lives in the structured profile (plus `last_asked` and the latest search summary) that is injected into
  every call, which is the memory the agent is meant to rely on anyway.
- **Eval runs split across quota windows on one commit.** One run per case (three were planned). A full pass
  stops cleanly when the quota runs out and `--resume` finishes the remaining cases later; resuming is refused
  if the code changed, the tree is dirty, or the model differs, so every result in a pass comes from one commit.
