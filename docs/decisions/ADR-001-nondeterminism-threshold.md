# ADR-001: Nondeterminism threshold strategy

**Status:** Accepted
**Date:** October 1, 2026
**Author:** Atif Osmani

## Context

LLM outputs vary run to run. The same prompt and input can produce different extractions on consecutive calls: a field that was correctly `UNKNOWN` on one run gets fabricated on the next, or a correctly extracted value gets paraphrased into something the containment check doesn't match.

This creates a fundamental problem for a pass/fail gate: if the eval is too strict, it fails on natural variance (false positive). If it's too loose, it misses real regressions (false negative). The threshold determines whether teams trust the gate or ignore it.

## Options considered

### Option 1: Strict exact match

Every field must match the expected output exactly, character for character.

- **Pro:** Simple to implement. No ambiguity about what "pass" means.
- **Con:** Fails constantly on nondeterministic outputs. A model that returns `"October 15, 2026"` vs `"Oct 15, 2026"` fails even though both are correct. Teams turn off the gate within a week.
- **Verdict:** Too brittle. Unusable for LLM outputs.

### Option 2: Fuzzy match with fixed tolerance

Allow a configurable percentage of fields to differ between runs. For example, "pass if 90% of fields are correct."

- **Pro:** Absorbs some nondeterministic variance.
- **Con:** What tolerance? 90% is too loose for a 12-case suite (10 fields wrong is fine?). 99% is too tight for small suites. The right number depends on the model, the prompt, and the case set, and there's no principled way to pick it without empirical data. A fixed tolerance also treats all failures equally: one fabrication and one formatting difference both count as one miss.
- **Verdict:** Better than exact match, but the tolerance is a magic number.

### Option 3: Judge-based scoring

Use a second LLM call to judge whether the output is semantically correct, even if the text differs.

- **Pro:** Handles paraphrasing, format variation, and edge cases that containment matching misses.
- **Con:** Expensive (doubles the API cost per eval run). Adds its own nondeterminism (the judge can disagree with itself). Slower. Makes the eval dependent on a second model's behavior, which can also change.
- **Verdict:** Useful for subjective quality, but overkill for factual extraction where we can define "correct" structurally.

## Decision

**Layered assertion strategy**, applied in order of increasing cost:

### Layer 1: Structural assertions (free, deterministic)

- Output parses as valid JSON.
- All nine expected fields are present.
- Fields marked as absent in the source are `UNKNOWN` (case-insensitive).

These are binary. A structural failure is always a real failure, never nondeterministic variance.

### Layer 2: Fuzzy semantic matching (free, tolerates surface variation)

- Normalize both expected and actual values: lowercase, collapse whitespace, strip punctuation.
- Check containment: does the normalized expected value appear within the normalized actual value?
- Flag numbers in the output that don't appear anywhere in the source text.

This absorbs formatting differences (`"Oct 15"` vs `"October 15"` still fails, but `"Grand Ballroom, Marriott"` vs `"Marriott Grand Ballroom"` passes if either substring matches). Containment is a deliberate choice over equality: it's more tolerant of extra context the model adds around the correct value.

### Layer 3: Judge scoring (expensive, reserved for subjective quality)

Not implemented in v1. Reserved for future use when the harness expands beyond factual extraction to evaluate briefing prose quality (tone, conciseness, structure).

When implemented, the judge should:
- Use a different model than the drafter to avoid correlated failures.
- Score on a rubric (1-5), not binary pass/fail.
- Run only on cases that passed Layers 1-2, to avoid paying for judge calls on structurally broken outputs.

### Pass gate logic

The gate compares two eval runs (baseline vs candidate prompt) and fails the candidate if:

1. **Fabrication rate increases.** Any increase in the number of `fabricated` outcomes is a regression. This is the strictest check because fabrication is the highest-severity failure in a briefing.
2. **Recall drops below baseline minus tolerance.** The tolerance accounts for nondeterministic variance. Default: 2 fields (empirically, re-running the same prompt on the same cases produces +/- 1 field of variance on recall; 2 gives margin).
3. **New invented numbers appear.** A number in the output that wasn't in the source is always suspicious.

The tolerance value (currently 2) should be calibrated per model by running N identical eval passes and measuring the observed variance. See "What I'd build next" in the README for the automatic threshold tuning plan.

## Consequences

- **Teams can trust the gate for fabrication.** Zero tolerance on fabrication means a prompt that introduces hallucinations always fails, regardless of nondeterministic noise.
- **Recall tolerance requires calibration.** The default of 2 is a starting point. Teams using different models or larger case sets need to measure their own variance.
- **No judge cost in v1.** The eval runs are fast and cheap: no API calls beyond the drafter itself.
- **Containment matching has known blind spots.** It can't catch an invented venue appended after the correct city, or a paraphrased value that doesn't contain the expected substring. These are documented in the README's Limits section and are candidates for judge-based scoring in a future version.
