# Metrics

Metrics for the eval harness itself. These measure whether the harness is doing its job, not whether the drafter is good.

## Primary metrics

### False positive rate

**Definition:** The percentage of eval runs where the pass gate fails a prompt that has not actually changed.

**How to measure:** Run the same prompt against the same cases N times (N >= 10). Count how many runs the gate would fail compared to the first run's baseline. That count divided by N-1 is the false positive rate.

**Target:** < 5%.

**Why it matters:** A gate that fails on nondeterministic variance (not real regressions) gets ignored. Every false positive erodes trust. At > 10%, teams turn off the gate.

### Detection latency

**Definition:** Whether a real regression (a prompt change that increases fabrication or drops recall) is caught in the same eval run where it's introduced.

**How to measure:** Introduce known-bad prompt changes (remove the "say UNKNOWN" instruction, remove the "don't invent numbers" rule) and confirm the gate catches them.

**Target:** 100% of fabrication-inducing changes caught in the same run.

**Why it matters:** If the eval doesn't catch a bad change before it merges, the eval is decorative.

### Time per eval run

**Definition:** Wall-clock time to run all cases against one prompt, including API calls for real-model drafters.

**How to measure:** `time python3 evals.py --drafter anthropic --prompt prompts/flag_gaps.txt`

**Target:** < 60 seconds for the 12-case suite. < 5 minutes for a future 50-case suite.

**Why it matters:** An eval that takes 10 minutes doesn't get run on every commit. It becomes a nightly job, and regressions sit for hours.

## Drafter metrics (per eval run)

These are the metrics the harness reports for the drafter being tested.

### Recall on known fields

**Definition:** Of the fields where the source contained the answer, how many did the drafter extract correctly?

**Formula:** `count(correct) / count(fields where expected is not None)`

**Reported as:** `{correct}/{total}` and percentage.

### Fabrication rate

**Definition:** Of the fields where the source was silent, how many did the drafter fill in anyway?

**Formula:** `count(fabricated) / count(fields where expected is None)`

**Reported as:** `{fabricated}/{total}` and percentage. This is the most important number in the suite.

### Wrong values

**Definition:** Fields where the drafter returned something, but not the right thing. Distinct from fabrication (where there was no right thing) and from missed (where the drafter said UNKNOWN).

**Reported as:** Count.

### Missed fields

**Definition:** Fields where the source had the answer but the drafter said UNKNOWN.

**Reported as:** Count. A miss is better than a fabrication but worse than a correct extraction.

### Invented numbers

**Definition:** Cases where the drafter's output contains a number that doesn't appear anywhere in the source text.

**Reported as:** Count of cases (not count of numbers). Even one invented number in a briefing is a problem.

### Carried-over values (v2)

**Definition:** Fields that are wrong or invented *and* contain a value the source ties to something else: last year's figure, a superseded date, a forwarder's name, an introducer. Each case lists these as `forbidden` values.

**Reported as:** Count. This catches the error the invented-number check can't: a number that is in the source, but about a different event.

### Blanks not worded UNKNOWN (v2)

**Definition:** Fields where the drafter declined to answer in other words (`TBD`, `Not specified`). They score as blanks, not fabrications, and are counted here as a format-compliance number.

## Harness health metrics

### Scorer self-check pass rate

**Definition:** Whether the mock-faithful and mock-fabricator drafters produce the expected scores.

**How to measure:** `python3 -m unittest discover -s tests`

**Target:** 100%. A scorer bug means every eval result is suspect.

### Case coverage

**Current (v2):** 50 cases across 10 trap categories, each category with 3 to 7 cases: role confusion 7, stale info 7, attribution 7, missing field 6, pending info 5, distractor event 4, precision 4, vague quantity 4, correction 3, control 3.

**Target:** Met for count. Next is depth: 5+ cases per category, so one nondeterministic failure moves a category's rate by less than 20 points.

### Field coverage

**Definition:** How many cases leave each field absent (expected = None), so fabrication can be measured per field.

**Current (v2):** moderator 26, audience_size 11, date 4, format 3, location 2, requestor_name 2, requestor_org 1, event_name 0, ask 0.

**Target:** At least 3 per field. Not met for five fields. Moderator dominates the gaps, so the overall fabrication rate leans heavily on one field; report it per field before drawing conclusions.

### Answer-key agreement (v2)

**Definition:** Cohen's kappa between the answer key and an independent human labeler on "stated vs. not stated", over a 15-case sample stratified across categories.

**How to measure:** `agreement.py` (see the README).

**Target:** kappa above 0.8. Every disagreement gets a decision: fix the key, fix the case, or write the rule down.

**Current:** Not yet measured with a human labeler. An AI review of all 50 keys (October 31, 2026) found no wrong values and 14 edge cases; the fixes are in the CHANGELOG. That review is a check, not a substitute: a model reviewing a key written with a model's help shares its blind spots.

### Gate false-positive rate and detection power (v2)

See [ADR-002](decisions/ADR-002-v2-scoring-and-gate.md) for the simulation table. On simulated noise with 10 baseline runs: about 5% false positives with one candidate run, 2% to 5% with more; a doubled fabrication rate is caught 90% of the time with 3 candidate runs and 100% with 10. Real-model numbers come from `python3 evals.py calibrate`.
