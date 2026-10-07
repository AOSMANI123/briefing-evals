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

## Harness health metrics

### Scorer self-check pass rate

**Definition:** Whether the mock-faithful and mock-fabricator drafters produce the expected scores.

**How to measure:** `python3 -m unittest discover -s tests`

**Target:** 100%. A scorer bug means every eval result is suspect.

### Case coverage

**Definition:** The number and variety of traps in the case set.

**Current:** 12 cases, each with one trap. No duplicate trap types.

**Target:** 50+ cases with multiple instances of each trap type, to reduce the impact of any single nondeterministic failure on the aggregate metrics.

### Field coverage

**Definition:** The percentage of the nine briefing fields that are tested in "absent" conditions (expected = None) across the case set.

**Current:** All nine fields are tested as absent in at least one case.

**Target:** Each field is absent in at least three cases, so fabrication detection per field is statistically meaningful.
