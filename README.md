# Briefing Evals

A test harness that checks whether an AI makes up facts when it drafts an executive briefing. It gives a model 50 fictional speaking invitations, each with a deliberate trap, and scores whether the model admits a gap or fills it with a plausible guess.

v2 turns it from a prompt test into a **model-readiness test**: repeated runs, a pass gate calibrated to measured noise, a side-by-side across model providers, failures sorted by what would fix them, and a way to check the answer key against an independent labeler.

---

## What it does

- **50 test cases in 10 trap categories:** missing fields, vague quantities ("a packed house"), stale information (last year's date or moderator), pending details, attribution (forwarded twice, a logistics contact, a mutual contact), role confusion (an introducer is not a moderator), distractor events, precision, corrections, and controls.
- **An answer key** for nine briefing fields per case. `null` means the source doesn't state it for this event. Many cases also list `forbidden` values: things the source says about a different event, year or person.
- **A scorer** that reports recall, fabrication, wrong values, carried-over values, and numbers that aren't in the source. Honest blanks count as blanks in any wording (`TBD`, `Not specified`).
- **Repeated runs** with `--runs N`, reported as a mean and range.
- **A pass gate** that fails a prompt or model change only when a metric moves more than run-to-run noise explains.
- **Failure grouping** that sorts each failure into prompt-fixable, persistent, introduced, or flaky.
- **Drafters for three providers** (Anthropic, OpenAI, Google), with token counts, latency and cost.
- **An agreement kit** that measures the answer key against an independent human labeler (Cohen's kappa).

---

## How it works

```
 cases/*.json  (source email + answer key + forbidden values)
        │
        ▼
 drafter (mock, Anthropic, OpenAI or Google) + a prompt  × N runs
        │
        ▼
 scorer: structure → honest blanks → containment → forbidden values → invented numbers
        │
        ▼
 run record (JSON)  ──►  compare (gate + failure groups)  ──►  readiness memo
                    ──►  calibrate (gate false-positive rate)
                    ──►  table (models side by side)
```

---

## Repo contents

```
briefing-evals/
├── evals.py                 # Scorer, drafters, repeated runs, gate, CLI
├── agreement.py             # Answer key vs. an independent labeler (Cohen's kappa)
├── prompts/
│   ├── naive.txt            # "Fill in the briefing details"
│   ├── flag_gaps.txt        # v1 rules: UNKNOWN beats a guess
│   └── flag_gaps_v2.txt     # v2: adds a definition for every field
├── cases/                   # 50 fictional requests with answer keys
├── labels/                  # Labeling packet, blank sheet, key export (15-case sample)
├── tests/test_evals.py      # Scorer, answer-key self-checks, gate, agreement math
├── docs/
│   ├── readiness-memo.md    # Template for the ship / don't-ship call
│   ├── case-study.md        # v1 write-up, including the first real run
│   ├── metrics.md
│   └── decisions/
│       ├── ADR-001-nondeterminism-threshold.md
│       └── ADR-002-v2-scoring-and-gate.md
└── CHANGELOG.md
```

---

## Prerequisites

- Python 3.10 or newer. No dependencies for the scorer, gate or tests.
- For real-model runs: the SDK and API key for each provider you test (`pip install anthropic`, `openai` or `google-genai`).

---

## Setup and run

### 1. Get it

```bash
git clone https://github.com/AOSMANI123/briefing-evals.git
cd briefing-evals
```

### 2. Check the harness (no key needed)

```bash
python3 -m unittest discover -s tests
python3 evals.py --drafter mock-faithful          # should score 100%, 0 fabrications
python3 evals.py --drafter mock-fabricator        # should be caught on every gap
python3 evals.py --drafter mock-noisy --runs 10 --out runs/sim.json
python3 evals.py calibrate runs/sim.json          # gate false-positive rate on simulated noise
```

`mock-noisy` is a seeded simulation, not a model. It exists to test the gate offline.

### 3. Test real models

Use each provider's exact model ID. Prices are per million tokens, from the provider's current pricing page; leave them off and cost is reported as n/a.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install anthropic openai google-genai
export ANTHROPIC_API_KEY=... OPENAI_API_KEY=... GEMINI_API_KEY=...   # never commit these

# Baseline: 10 runs. Candidate: at least 3.
python3 evals.py --drafter anthropic --model <id> --prompt prompts/flag_gaps.txt \
    --runs 10 --price-in <usd> --price-out <usd> --out runs/claude-v1.json
python3 evals.py --drafter anthropic --model <id> --prompt prompts/flag_gaps_v2.txt \
    --runs 3 --out runs/claude-v2.json

python3 evals.py compare runs/claude-v1.json runs/claude-v2.json   # exits 1 if the gate fails
python3 evals.py calibrate runs/claude-v1.json
python3 evals.py table runs/*.json                                 # paste into the readiness memo
```

Add `--category stale_info` (or any category) to run one trap type.

### 4. Check the answer key

```bash
python3 agreement.py agree labels/key.csv labels/<labeler>.csv
```

Give a second person `labels/packet.md` and a copy of `labels/blank.csv`. They fill in each field without seeing the key. A kappa above 0.8 on "stated vs. not stated" means the key is solid. Every disagreement gets a decision: fix the key, fix the case, or write the rule down.

---

## The pass gate

The gate fails a candidate if fabrications, carried-over values, invented numbers or parse errors go up, or correct fields go down, by more than:

```
2.5 × (baseline standard deviation across runs) × sqrt(1/N_baseline + 1/N_candidate)
```

Tested on simulated noise with 10 baseline runs, it fails an unchanged prompt about 2% to 5% of the time. It catches a doubled fabrication rate 90% of the time with 3 candidate runs, and 100% of the time with 10. The first version of the gate, which used the baseline's max-minus-min range, got *less* sensitive with more runs, so it was replaced before shipping. Details are in [ADR-002](docs/decisions/ADR-002-v2-scoring-and-gate.md).

## Failure groups

`compare` sorts every failing case and field by what would fix it:

| Group | Meaning | Usual fix |
|---|---|---|
| Fixed by the candidate | Failed under the baseline, never under the candidate | The prompt change worked |
| Persistent | Fails under both | Schema, answer key, or the model itself |
| Introduced | New in the candidate | Regression: don't ship it |
| Flaky | Fails in some runs | Run more before deciding |

In v1, the emcee-as-moderator error persisted under both prompts. It turned out to be a definition problem, not a prompt problem. This grouping makes that call from data.

---

## Prompts

| Prompt | What it says |
|---|---|
| [`naive.txt`](prompts/naive.txt) | Read the request and fill in the briefing details. |
| [`flag_gaps.txt`](prompts/flag_gaps.txt) | Use only facts about this event. Write `UNKNOWN` if it isn't stated or is TBD. The forwarder isn't the requestor. Copy numbers exactly. |
| [`flag_gaps_v2.txt`](prompts/flag_gaps_v2.txt) | v1's rules, plus a definition for each field: who counts as the moderator, that venue capacity isn't audience size, that corrections override earlier lines. |

---

## Results

### v2 (50 cases): not yet run on a real model

The harness, gate and cases are built and tested offline. Real-model runs need API keys and are the next step. Results will go in the [readiness memo](docs/readiness-memo.md), not here, until they exist.

### v1 (12 cases): October 7, 2026, `claude-sonnet-5`, one run per prompt

| Prompt | Recall | Fabrication (as scored) |
|---|---|---|
| Naive | 96/96 | 10/12 |
| Flag gaps | 92/96 | 1/12 |

**The headline was misleading, and that was the finding.** Seven of the naive prompt's ten "fabrications" were the model writing "TBD" or "Not specified" instead of the exact word `UNKNOWN`. Three were real: last year's audience size carried into this year's briefing, a team name put in a person's name field, and an emcee labeled as the moderator. The rules prompt fixed two of the three, and cost 4 stated fields along the way. The full analysis is in the [case study](docs/case-study.md).

v1 numbers aren't directly comparable to v2. Building v2 showed that the v1 answer key contradicted itself on who counts as a moderator, so two v1 answers changed. See the [CHANGELOG](CHANGELOG.md).

---

## Limits

- Fabrication coverage leans on one field. 26 of the 49 gaps are the moderator field, and event name and ask are never absent. Report fabrication per field before drawing conclusions.
- All cases are fictional and written by one person with AI help. An AI review checked every key and found no wrong values, but a model checking a key written with a model's help shares its blind spots. The human-labeler check hasn't been run yet.
- Matching is word-level containment, so it can't catch an invented venue added next to the correct city.
- It checks the structured fact block, not the prose of the briefing.
- Organization and person names are invented. Any match to a real one is unintended.

---

## Related

- [Engagement Agents](https://github.com/AOSMANI123/engagement-agents): uses the v1 requests as sample data, and its validator catches the stale-number failure found here
- [Portfolio](https://aosmani123.github.io)
