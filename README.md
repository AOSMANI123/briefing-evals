# Briefing Evals

A small test harness that checks whether an AI makes up facts when it drafts a briefing. It gives a model 12 fictional speaking invitations, each with something deliberately missing, and scores whether the model admits the gap or fills it with a plausible guess.

---

## What it does

- **12 test cases**, each a fictional request with a trap: no moderator, last year's date, a forwarded email, a vague crowd size, two events in one message.
- **An answer key** for nine briefing fields per case, with `null` where the source says nothing.
- **A scorer** that reports recall on stated fields, the fabrication rate on unstated ones, wrong values, any number that isn't in the source, and any figure from a past event carried into this year's fields. Honest blanks count as blanks in any common wording ("Not specified", "TBD"), and are reported separately as a format issue.
- **Two prompts to compare:** a vague one and one with explicit rules.
- **Mock drafters** that prove the scorer works with no API key.

---

## How it works

```
 cases/*.json  (source email + answer key)
        │
        ▼
 drafter (mock or Claude) + a prompt from prompts/
        │
        ▼
 JSON with 9 fields
        │
        ▼
 scorer: structure → honest blanks → containment → fabrication → invented numbers → prior-year figures
        │
        ▼
 recall · fabrication rate · wrong values · per-case failures
```

---

## Repo contents

```
briefing-evals/
├── evals.py                 # Drafters, scorer and CLI
├── prompts/
│   ├── naive.txt            # "Fill in the briefing details"
│   └── flag_gaps.txt        # Explicit rules: UNKNOWN beats a guess
├── cases/                   # 12 fictional requests with answer keys
├── tests/test_evals.py      # Proves the scorer works
├── docs/
│   ├── case-study.md        # Full write-up, including the first real run
│   ├── metrics.md
│   └── decisions/
│       └── ADR-001-nondeterminism-threshold.md
└── CHANGELOG.md
```

---

## Prerequisites

- Python 3.10 or newer
- For real-model runs only: `pip install anthropic` and an [Anthropic API key](https://console.anthropic.com)

---

## Setup and run

### 1. Get it

```bash
git clone https://github.com/AOSMANI123/briefing-evals.git
cd briefing-evals
```

### 2. Check the scorer (no key needed)

```bash
python3 -m unittest discover -s tests
python3 evals.py --drafter mock-faithful     # should score 100%, 0 fabrications
python3 evals.py --drafter mock-fabricator   # should be caught on all 12 gaps
python3 evals.py --drafter mock-honest-wording  # says "TBD" instead of UNKNOWN: 0 fabrications, 12 format notes
python3 evals.py --drafter mock-stale        # copies last year's figures: both caught as prior-year
```

### 3. Test a real model

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install anthropic
export ANTHROPIC_API_KEY=...        # never commit this
python3 evals.py --drafter anthropic --prompt prompts/naive.txt
python3 evals.py --drafter anthropic --prompt prompts/flag_gaps.txt
```

Add `--out results.json` to save per-field results.

---

## Prompts

| Prompt | What it says |
|---|---|
| [`naive.txt`](prompts/naive.txt) | Read the request and fill in the briefing details. |
| [`flag_gaps.txt`](prompts/flag_gaps.txt) | Use only facts about this event. Write `UNKNOWN` if it isn't stated or is TBD. The forwarder isn't the requestor. Copy numbers exactly. |

---

## Results

First real run, October 7, 2026, `claude-sonnet-5`, one run per prompt:

| Prompt | Recall | Fabrication (as scored) |
|---|---|---|
| Naive | 96/96 | 10/12 |
| Flag gaps | 92/96 | 1/12 |

**The headline is misleading, and that's the finding.** Seven of the naive prompt's ten "fabrications" were the model writing "TBD" or "Not specified" instead of the exact word `UNKNOWN`. Three were real: last year's audience size carried into this year's briefing, a team name put in a person's name field, and an emcee labeled as the moderator. The rules prompt fixed two of the three, and cost 4 stated fields along the way.

The full analysis, and what it changed about the scorer, is in the [case study](docs/case-study.md). The v2 scorer now applies the first two fixes from that analysis: honest blanks in any wording count as blanks, and a field-level check keeps last year's figures out of this year's fields. The October 7 numbers above were scored with the v1 scorer and haven't been re-run yet.

---

## Related

- [Engagement Agents](https://github.com/AOSMANI123/engagement-agents): uses these 12 requests as sample data, and its validator catches the stale-number failure found here
- [Portfolio](https://aosmani123.github.io)
