# Changelog

All notable changes to this project will be documented in this file. Format follows [Keep a Changelog](https://keepachangelog.com/).

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
