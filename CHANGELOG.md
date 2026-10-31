# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [0.3.0] - October 31, 2026

### Added
- 38 new cases (50 total) across 10 trap categories, each tagged with a `category`.
- `forbidden` values per case: strings from the source that belong to a different event, year, person or role. A field that is wrong or invented and contains one is flagged `carried_over`.
- `--runs N` for repeated runs, reported as mean and range, saved as one JSON record.
- `compare`: noise-calibrated pass gate (exits 1 on failure) plus failure grouping into fixed, persistent, introduced and flaky.
- `calibrate`: leave-one-out false-positive rate for the gate.
- `table`: markdown table of saved runs for the readiness memo.
- OpenAI and Google drafters alongside Anthropic, with `--model` required, plus token counts, latency, and cost from user-supplied prices.
- `mock-noisy`: a seeded simulated drafter for testing the gate offline.
- `agreement.py` and `labels/`: a stratified 15-case labeling packet and Cohen's kappa against an independent labeler.
- `prompts/flag_gaps_v2.txt` with a definition for every field.
- ADR-002 and a readiness-memo template.
- Tests that check the answer key itself (stated values and forbidden values must appear in the source).

### Changed
- Honest blanks in any wording (`TBD`, `Not specified`, `N/A`) score as blanks, not fabrications. They are counted separately as a format-compliance number.
- Matching uses whole words (`600` no longer matches `6000`). `1,200` equals `1200`, and `30 minutes` matches `30-minute`.
- **Answer key: one rule for moderators.** The moderator leads the conversation or runs the panel; introducers, emcees and other panelists are not moderators. v1 contradicted itself here: case 02 followed this rule, but cases 09 and 12 did not. Both now expect no moderator.
- Case `09-complete` renamed to `09-introducer`, since it is no longer a complete control. Cases 13 to 15 are the new controls.
- Pass-gate logic in ADR-001 superseded by ADR-002.

### Fixed after an independent review of all 50 answer keys
- A correct value with an old value given as context ("May 13, moved from May 6") is now scored correct. The first draft scored it wrong.
- Wider accepted answers: case 11 format, case 08 ask, case 07 range wording, case 35 format (to match case 09).
- Case 08's date no longer accepts just the first day of a five-day event.
- Case 18 and case 33 organization names changed to clearly fictional ones.

## [0.2.0] - October 1, 2026

### Added
- PM PRFAQ-format README with problem statement, success metrics, scope decisions, and roadmap.
- ADR-001: Nondeterminism threshold strategy documenting the layered assertion approach (structural, fuzzy semantic, judge-reserved).
- Harness metrics documentation covering false positive rate, detection latency, and eval run time.
- This changelog.

### Changed
- README rewritten from project description to full PM skeleton (PRFAQ format) with "What I chose not to build" and "What I'd build next" sections.

## [0.1.0] - September 2026

### Added
- Initial eval harness (`evals.py`) with CLI interface.
- 12 fictional test cases in `cases/`, each with one trap and an answer key for nine briefing fields.
- Scoring engine: labels each field as `correct`, `missed`, `wrong`, `fabricated`, or `correct_unknown`.
- Invented-number detection: flags numbers in the output not present in the source.
- Two mock drafters (`mock-faithful`, `mock-fabricator`) for scorer self-checks.
- Anthropic API drafter integration.
- Two prompt versions: `prompts/naive.txt` and `prompts/flag_gaps.txt`.
- Unit tests for the scorer (`tests/test_evals.py`).
- Project page (`index.html`) for the portfolio site.
