# Model readiness memo: briefing fact-block drafter

**Status:** Template. No v2 real-model runs yet. Every bracketed item is filled from `evals.py` output, never estimated.
**Author:** Atif Osmani

---

## The call

[Ship / Ship with conditions / Don't ship] **[model ID] with [prompt file]** for drafting briefing fact blocks, with a person reviewing every block before it reaches the executive.

## Why

| Setup | Runs | Recall | Fabrication rate | Carried over | Invented numbers | Cost per run | Median s/case |
|---|---|---|---|---|---|---|---|
| [paste from `python3 evals.py table runs/*.json`] | | | | | | | |

Read the table this way. In an executive briefing, a guess is worse than a blank, so fabrication and carried-over values outrank recall. A model that misses a stated fact costs a person a minute to fill it in. A model that invents a moderator puts a wrong name in front of the CEO.

## What fails, and what would fix it

From `python3 evals.py compare runs/<baseline>.json runs/<candidate>.json`:

| Failure | Category | Share of runs | Group | Fix |
|---|---|---|---|---|
| [case, field, what it wrote] | [category] | [x%] | [persistent / fixed / introduced / flaky] | [prompt / schema / answer key / model] |

**Rule of thumb for the fix column:**
- **Fixed by a prompt change** means the instruction was missing.
- **Persistent under every prompt** means one of three things: the schema has no place for the fact (v1's emcee had nowhere to go but "moderator"), the answer key is debatable (check `agreement.py`), or the model doesn't have the behavior. Only that last one goes to a model provider or a fine-tuning conversation.
- **Flaky** means run more before deciding anything.

## How sure we are

- **Runs:** [N] per setup. The gate's allowance shrinks with more runs; see ADR-002.
- **Gate false-positive rate on real runs:** [from `python3 evals.py calibrate`]. Target under 5%.
- **Answer key agreement with an independent labeler:** kappa [x] on [n] fields. Target above 0.8.
- **Weakest part of the evidence:** [for example: event_name, ask and requestor_org are never absent in the case set, so fabrication on those fields is untested.]

## What would change this call

- [A fabrication rate above x% on a fresh set of real requests, rewritten as fiction.]
- [A labeler disagreement rate above y% on the moderator rule.]
- [A cheaper model reaching the same fabrication rate within the gate's noise.]

## Conditions for shipping

1. The human reviewer stays. The system drafts; a person sends.
2. The gate runs on every prompt change: 10 baseline runs, 3 candidate runs.
3. [Any setup-specific condition.]
