# Briefing Evals

**Golden-set regression testing for LLM-generated briefings.**

Independent work. Not affiliated with any employer.

---

## Problem

LLM features are reliability problems. Most teams shipping AI-powered features treat evaluation as an afterthought: they build a demo, eyeball the output, and ship. When a prompt change breaks something, they find out from a user, not a test. Prompt regression testing doesn't exist as a standard practice.

In executive briefings specifically, the failure mode is subtle and dangerous. A drafter that invents a moderator's name, carries forward last year's date, or converts "a big crowd" into "500 attendees" produces output that *looks* correct. The error reaches the executive's prep packet with no warning. A guess is worse than a blank.

## Why now

Every team shipping LLM features needs regression testing but builds it ad hoc. There is no lightweight, open harness that answers the basic question: "did my prompt change break something that was working?" The tooling gap means most teams either don't test at all or build one-off scripts that test the wrong thing (exact string matching against nondeterministic output).

## What it does

Golden-set regression testing for prompts, focused on factual accuracy in structured extraction tasks.

- **Versioned prompts.** Each prompt is a text file. You can diff two versions and trace when a behavior changed.
- **Fixture set of inputs with expected properties.** Twelve fictional engagement requests, each with an answer key for nine briefing fields and one deliberate trap (a missing moderator, a forwarded email, a vague audience size).
- **Assertions that survive nondeterminism.** Three layers:
  - *Structural:* Does the output parse as valid JSON with the expected fields?
  - *Containment:* Does the extracted value contain the expected text (normalized)?
  - *Fabrication detection:* Did the drafter fill in a field the source left blank? Did it introduce numbers not present in the source?
- **Side-by-side diff of two prompt versions.** Run the same cases against two prompts and compare recall, fabrication rate, wrong values, and invented numbers.
- **Pass gate that blocks regressions.** A prompt version that increases the fabrication rate or drops recall below a threshold fails the eval. The gate is designed to catch real regressions, not penalize nondeterministic variance.

## How I measure success

| Metric | Target | Why it matters |
|---|---|---|
| False positive rate on the pass gate | < 5% across 10 identical runs | A gate that cries wolf gets turned off |
| Time to detect a real regression | Same commit | If the eval doesn't catch a fabrication-inducing prompt change before merge, it's decorative |
| Developer adoption (if open-sourced) | N/A for now | Would validate that the harness generalizes beyond briefings |

## Results

First real-model run: October 7, 2026, `claude-sonnet-5`, one run per prompt.

| Drafter | Recall | Fabrication rate (as scored) | Status |
|---|---|---|---|
| mock-faithful (scorer self-check) | 96/96 | 0/12 | Verified |
| mock-fabricator (scorer self-check) | 96/96 | 12/12 caught | Verified |
| Real model, naive prompt | 96/96 (100%) | 10/12 (83%) | Run once |
| Real model, flag-gaps prompt | 92/96 (96%) | 1/12 (8%) | Run once |

Wrong values: 0 in both runs. Invented numbers: 0 in both runs.

### What the failures actually were

The headline says the gap-flagging prompt cut fabrication from 83% to 8%. Reading each failure tells a more useful story.

**Most of the naive prompt's "fabrications" were honest answers in the wrong words.** Seven of the ten flagged fields were the model declining to guess, just not in the format the scorer expects: `"Not specified"`, `"TBD"`, `"TBD (not yet locked…)"`. The scorer only counts the literal `UNKNOWN` as a blank, so it scored those as fabrications. The naive prompt never asked for `UNKNOWN`, so this measures format compliance as much as honesty.

**Three were real problems:**

| Case | What the model wrote | Why it matters |
|---|---|---|
| 05 virtual | audience_size: `"40,000 (based on last year's stream)"` | The trap worked: last year's number was carried into this year's briefing. The invented-number check missed it because 40,000 *is* in the source, just about a different event. |
| 11 no signature | requestor_name: `"Pacific Retail Association events team"` | No person signed the email; the model filled the name field with a team. |
| 02 vague crowd | moderator: `"Priya Nand"` | Priya is named in the source as the emcee who introduces the keynote, not a moderator. A role mix-up, not an invented person. |

**The gap-flagging prompt fixed two of the three.** Only the Priya Nand case survived, and it appeared under both prompts. That points at the schema rather than the prompt: there is no field for "introducer," so the model reaches for the nearest one.

**It cost some recall.** The stricter prompt marked 4 fields `UNKNOWN` that the source did state. A blank is still safer than a guess in an executive briefing, but it is a real trade-off and worth measuring rather than assuming.

So the honest real-world fabrication count under the naive prompt is closer to 3 of 12 than 10 of 12, and the stricter prompt brings it to 1.

### What this changed about the harness

1. **The scorer should accept honest blanks in any wording.** Treat `Not specified`, `TBD`, `N/A` and similar as `UNKNOWN`, so the fabrication metric measures invention, not formatting. Otherwise the naive prompt looks far worse than it is, and a team might "fix" the wrong problem.
2. **The invented-number check needs context.** A number copied from the source can still be wrong if it describes a different event. Case 05 needs a field-level check that last year's figures stay out of this year's fields.
3. **Case 02's answer key needs a decision.** Either add an introducer field or document that an emcee is not a moderator.
4. **Run each prompt several times before trusting a gate.** These are single runs. The nondeterminism threshold in [ADR-001](decisions/ADR-001-nondeterminism-threshold.md) still needs N repeated runs to calibrate.

The mock rows prove the scorer works mechanically: a perfect drafter gets full marks, and every invented value from a bad drafter is caught. The real-model rows show that "works mechanically" and "measures the right thing" are different claims.

## Architecture

```
cases/           12 fictional engagement requests (JSON fixtures)
prompts/         Versioned prompt files (naive.txt, flag_gaps.txt)
evals.py         Scorer + CLI: run cases, score outputs, print summary
tests/           Unit tests for the scorer itself
docs/decisions/  Architecture decision records
```

### Scoring

The drafter returns JSON with nine fields. Each field is scored as one of:

| Outcome | Meaning |
|---|---|
| `correct` | Expected value found in the output |
| `missed` | Source had the answer; drafter said UNKNOWN |
| `wrong` | Drafter returned a value, but not the right one |
| `fabricated` | Source was silent; drafter filled it in anyway |
| `correct_unknown` | Source was silent; drafter correctly said UNKNOWN |

The scorer also flags any number in the output that doesn't appear in the source text.

### The traps

| Case | Trap | Right answer |
|---|---|---|
| No moderator | Nobody is named as moderator | `UNKNOWN` |
| Vague crowd | "Always draws a big crowd" | Audience size `UNKNOWN`, no number |
| Last year's date | Only last year's date appears | Date `UNKNOWN` |
| Forwarded | A colleague forwarded the request | The original sender, not the forwarder |
| Virtual | Online event; last year's viewership mentioned | Location "virtual," audience `UNKNOWN` |
| Two events | One event mentioned only to rule it out | The event actually being asked about |
| Range | "250-300 people" | The range, not an average |
| Open format | "Flexible on what that looks like" | Format `UNKNOWN` |
| Complete | Everything is stated (control) | All nine fields |
| TBD moderator | "Moderator: TBD" | `UNKNOWN` |
| No signature | Signed only by "events team" | Requestor name `UNKNOWN` |
| Pending venue | City known, venue pending | The city only |

## Run it

```bash
# Check the scorer works (no API key needed)
python3 -m unittest discover -s tests
python3 evals.py --drafter mock-faithful     # should score 100%, 0 fabrications
python3 evals.py --drafter mock-fabricator   # should be caught on all 12 gaps

# Test a real model
pip install anthropic
export ANTHROPIC_API_KEY=...
python3 evals.py --drafter anthropic --prompt prompts/naive.txt
python3 evals.py --drafter anthropic --prompt prompts/flag_gaps.txt
```

## What I chose not to build

- **Full CI/CD integration.** That's infrastructure, not the eval itself. The harness is a Python script you can call from any CI system, but wiring it into GitHub Actions or Jenkins is out of scope.
- **A visual dashboard.** The CLI output is the MVP. A pass/fail signal and a per-case breakdown in the terminal is enough to act on. Dashboards are where eval projects go to die.
- **Support for image/multimodal inputs.** The cases are text-in, JSON-out. Multimodal evaluation is a different problem with different assertion strategies.
- **Prompt optimization.** This harness measures whether a prompt works, not which prompt is best. Optimization is a search problem; this is a regression gate.

## What I'd build next

1. **CI integration.** A GitHub Action that runs the eval on every PR that touches a prompt file, with a comment showing the diff in pass rate.
2. **Cost tracking per eval run.** Log token counts and estimated cost so teams can budget their eval runs and catch prompt changes that silently double the cost.
3. **Automatic threshold tuning.** Run N identical eval passes to measure the natural variance of a prompt, then set the pass gate threshold to the 95th percentile of that variance. Replaces manual threshold guessing.
4. **Larger case library.** 50+ cases drawn from the patterns that appear in real engagement requests, with every detail rewritten as fictional.

## Limits

- Twelve cases is a starting set, not a benchmark.
- Matching is simple text containment, so it can't catch an invented venue added next to the correct city.
- It checks the structured fact block, not the prose of the briefing.
- The pass gate threshold (see [ADR-001](decisions/ADR-001-nondeterminism-threshold.md)) requires empirical calibration per model and prompt pair.

## License

MIT
