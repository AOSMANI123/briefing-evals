# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/).

## [Unreleased]

Briefing Evals v2, step 1: fix the scorer using the v1 real-model findings.

### Added
- Prior-year check: cases can list past-event figures under `prior_year`; any answered field containing one is flagged and counted.
- `prior_year` annotations for case 03 (last year's date) and case 05 (last year's 40,000 viewers).
- `mock-honest-wording` and `mock-stale` drafters, and 15 new scorer tests, including a check that every case mentioning "last year" is annotated.
- Two new summary lines: prior-year figures, and blanks not written as `UNKNOWN`.

### Changed
- Honest blanks in common wordings ("Not specified", "TBD", "N/A", "Pending", "To be confirmed", "Not stated in the request") now score as blanks instead of fabrications. The first clause of the value decides, so "Cleveland (venue pending)" still counts as an answer.

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
