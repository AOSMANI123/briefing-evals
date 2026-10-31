# ADR-002: v2 scoring rules and a noise-calibrated pass gate

**Status:** Accepted
**Date:** October 31, 2026
**Author:** Atif Osmani
**Supersedes:** the pass-gate logic in [ADR-001](ADR-001-nondeterminism-threshold.md). ADR-001's layered assertions still stand.

## Context

The first real-model run (October 7, 2026) showed that the harness measured the wrong thing in three places:

1. **Honest blanks scored as fabrications.** Seven of the naive prompt's ten "fabrications" were the model writing `TBD` or `Not specified` instead of the literal `UNKNOWN`.
2. **Stale numbers slipped through.** In case 05 the model carried last year's 40,000 viewers into this year's audience field. The invented-number check missed it because 40,000 is in the source, just about a different event.
3. **The answer key disagreed with itself on "moderator."** Case 02 said an emcee who introduces a keynote is not a moderator. Case 09 counted a college president who introduces the speaker as the moderator, and case 12 counted a director who "would host" a keynote as one. A model can't be right on all three.

The gate in ADR-001 also had a fixed recall tolerance of 2 fields and zero tolerance on fabrication. With nondeterministic models, zero tolerance fails unchanged prompts, and a fixed number has nothing behind it.

## Decisions

### 1. Any honest blank counts as a blank

`UNKNOWN`, `TBD`, `TBC`, `N/A`, `Not specified`, `To be confirmed` and similar all score as blanks. A trailing parenthetical is ignored, so `TBD (not yet locked)` is a blank, while `Chicago (venue TBD)` is a value. Blanks not written as `UNKNOWN` are counted separately as a format-compliance number, so the information isn't lost.

### 2. Cases can name values that must not appear in a field

Each case can list `forbidden` values: strings that are in the source but belong to a different event, year, person or role (last year's attendance, a forwarder's name, an introducer, a superseded date). If one shows up in a field that is otherwise wrong or invented, the field is flagged `carried_over`. A correct value with the old one as context ("May 13, 2027 (moved from May 6)") stays `correct`: that is a helpful briefing, not an error. An independent review of the answer key pushed this rule; the first draft penalized it.

### 3. The moderator rule

The moderator is **the person who leads the conversation with the CEO or runs the panel.** Someone who only introduces, welcomes or emcees is not the moderator, and neither are other panelists. A host who will interview the CEO (cases 05, 07) is. Under this rule, cases 09 and 12 now expect no moderator. Case 09 was renamed `09-introducer`, since it is no longer a complete control case. Three new control cases (13 to 15) replace it.

The rule is written into the new prompt, [`flag_gaps_v2.txt`](../../prompts/flag_gaps_v2.txt), along with a definition for every field. That makes it a fair test: the model is told the rule it is scored on.

**Consequence:** v1 results were scored against the old key and are not directly comparable to v2 results.

### 4. Matching uses whole words, and numbers ignore commas

`600` no longer matches inside `6000`, and `1,200` equals `1200`.

### 5. The gate measures noise instead of assuming it

Run each prompt N times. The gate fails the candidate if any gated metric (fabricated fields, carried-over values, cases with invented numbers, parse errors, or correct known fields) moves the wrong way by more than:

```
allowed = 2.5 × (baseline standard deviation) × sqrt(1/N_baseline + 1/N_candidate)
```

More runs on either side shrink the allowance, so the gate gets sharper as evidence grows. With fewer than two baseline runs there is no noise estimate, so any regression fails and the output says the gate is uncalibrated.

**Why not the first version of this ADR's rule** (allowed = the baseline's max minus min): it was tested on simulated noise before shipping, and it got *less* sensitive as the candidate ran more times, because the allowance never shrank. With 10 candidate runs it caught a doubled fabrication rate only 5% of the time.

### How the gate was tested

A simulated drafter (`mock-noisy`) fabricates on each missing field with probability p and drops a known field with probability 0.04, seeded so results repeat. The baseline was p = 0.10. Share of trials (40 each) in which the gate failed the candidate:

| Baseline runs | Candidate p | 1 candidate run | 3 runs | 10 runs |
|---|---|---|---|---|
| 10 | 0.10 (unchanged) | 5% | 5% | 2% |
| 10 | 0.15 | 18% | 35% | 55% |
| 10 | 0.20 (doubled) | 57% | 90% | 100% |
| 10 | 0.25 | 72% | 98% | 100% |
| 5 | 0.10 (unchanged) | 12% | 10% | 12% |
| 5 | 0.20 (doubled) | 60% | 82% | 92% |

The first row is the false-positive rate; the target is under 5%. The rest show detection power.

**Recommendation:** at least 10 baseline runs and 3 candidate runs per prompt change. Five baseline runs is too few: the false-positive rate roughly doubles. These numbers come from a simulation, not a model. `python3 evals.py calibrate` measures the real false-positive rate once real runs exist.

### 6. Failures are sorted by what would fix them

`compare` sorts each failing case and field into one of four groups, using the share of runs in which it failed:

| Group | Rule | What it usually means |
|---|---|---|
| Fixed by the candidate | Failed in most baseline runs, never in the candidate | The prompt fixed it |
| Persistent | Failed in most runs under both | Look at the schema, the answer key or the model. A prompt change didn't help. |
| Introduced | Never failed in baseline, fails in most candidate runs | Regression |
| Flaky | Fails in some runs but not most | Nondeterminism. Run more before calling it. |

In v1, the Priya Nand error persisted under both prompts, and it turned out to be a definition problem rather than a prompt problem. This grouping makes that kind of call from data instead of by hand.

## Consequences

- Fabrication rates go down for prompts that never asked for the literal word `UNKNOWN`. That's correct: they were inflated.
- The gate costs more to run (10 + 3 suite runs per prompt change, instead of 1 + 1). That's the price of a gate people will trust.
- The answer key is now a claim to be checked, not an assumption. See `agreement.py` for measuring it against an independent labeler.
