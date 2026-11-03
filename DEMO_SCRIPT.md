# Demo script (about 2 minutes)

Record in Chrome at http://localhost:8000 (real model, `FAKE_LLM` unset). Have the eval report open in a second
tab (`evals/results.md` on GitHub, or the README section). Hold the button (or Space) while speaking.

Before recording: start a fresh conversation, allow the microphone, and say one throwaway line so the voice list
and the first request are warm. Then press **New conversation**.

---

## 0:00 to 0:15. Intro (screen: empty app)

> "This is a voice agent that takes a renter from 'I need a home' to a grounded shortlist. On the right is its
> memory: a structured renter profile, not the chat log. The listings are synthetic demo data."

## 0:15 to 0:50. A normal conversation (screen: transcript + memory panel)

Speak:

> **"Hi, I need a 2 BHK in Sector 56 or Sector 57, budget around 30 thousand."**

Point at the panel: budget, areas and BHK fill in; "Agent is asking for" shows move-in and commute.

> **"Moving in on the 1st of December, and my office is in Cyber City."**

The agent reads the profile back. Point at the stage: "Read back to renter, waiting for a yes".

> "The read-back is generated from the profile in code, so it can't misquote the memory. It won't search until I
> say yes."

## 0:50 to 1:20. Budget change, live in memory

Instead of confirming, speak:

> **"Actually, make it 35 thousand."**

Point at:
- the green correction line in the reply ("Updated … ₹30,000 -> ₹35,000");
- the budget field flashing in the panel;
- the changelog entry tagged **correction**;
- the stage dropping back to "waiting for a yes" (any change resets confirmation).

Then say:

> **"Yes, that's right."**

## 1:20 to 1:40. Grounded shortlist

Three cards appear. Point at:

> "Every price, deposit and distance here is rendered from the listings data by the server. The model only picks
> listing ids from the search result and writes one trade-off line, like the one that's over budget but
> available. If no listing matched, it would say so and show nothing."

Point at the latency strip: STT, model time and number of calls, TTS start. Mention that quota waits are shown
separately and excluded from total.

Optional, if time allows: try a little Hinglish, e.g. **"Pets allowed hai kya?"**

## 1:40 to 2:00. Evals (screen: results table)

> "Behind it is a text-mode eval harness: 12 scripted conversations (vague, contradictory, Hinglish, budget
> changes, a listing that doesn't exist, prompt injection, and a city-level request with a relative date). The
> checks are deterministic: they read the tool log and structured fields against the dataset, with no LLM
> judge. Here's the pass rate on one commit, with failures listed honestly."

Close on the table.

---

**Fallbacks while recording:** if the mic misbehaves, type the same lines into the text box; everything else is
identical. If Groq rate-limits, the status line shows the error. Wait a minute and resend, or record that
segment again.
