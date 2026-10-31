"""Checks that the scorer rewards a faithful drafter and catches a fabricating one.
Run: python3 -m unittest discover -s tests
"""
import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import evals  # noqa: E402


class ScorerTests(unittest.TestCase):
    def setUp(self):
        self.cases = evals.load_cases()

    def test_cases_load_with_enough_gaps(self):
        self.assertEqual(len(self.cases), 12)
        gaps = sum(1 for c in self.cases for f in evals.FIELDS if c.expected[f] is None)
        self.assertGreaterEqual(gaps, 10)
        control = next(c for c in self.cases if c.id == "09-complete")
        self.assertTrue(all(control.expected[f] is not None for f in evals.FIELDS))

    def test_faithful_drafter_scores_perfectly(self):
        res = [evals.score_case(c, evals.mock_faithful(c, "")) for c in self.cases]
        s = evals.summarize(res, self.cases)
        self.assertEqual(s.recall, 1.0)
        self.assertEqual(s.fabricated, 0)
        self.assertEqual(s.invented_number_cases, 0)

    def test_fabricator_is_caught_on_every_gap(self):
        res = [evals.score_case(c, evals.mock_fabricator(c, "")) for c in self.cases]
        s = evals.summarize(res, self.cases)
        self.assertEqual(s.fabricated, s.unknown_total)
        self.assertGreater(s.invented_number_cases, 0)

    def test_last_years_date_counts_as_fabrication(self):
        case = next(c for c in self.cases if c.id == "03-last-years-date")
        out = evals.mock_faithful(case, "")
        out["date"] = "November 6, 2025"
        r = evals.score_case(case, out)
        self.assertEqual(next(f for f in r.fields if f.field == "date").outcome, "fabricated")

    def test_rounded_range_is_wrong(self):
        case = next(c for c in self.cases if c.id == "07-range")
        out = evals.mock_faithful(case, "")
        out["audience_size"] = "275"
        r = evals.score_case(case, out)
        self.assertEqual(next(f for f in r.fields if f.field == "audience_size").outcome, "wrong")
        self.assertIn("275", r.invented_numbers)

    def test_forwarder_is_not_the_requestor(self):
        case = next(c for c in self.cases if c.id == "04-forwarded")
        out = evals.mock_faithful(case, "")
        out["requestor_name"] = "Chris"
        r = evals.score_case(case, out)
        self.assertEqual(next(f for f in r.fields if f.field == "requestor_name").outcome, "wrong")


class HonestBlankTests(unittest.TestCase):
    """v1 finding: 7 of the naive prompt's 10 'fabrications' were honest blanks in
    other words. Those must score as blanks, and still be visible as a format issue."""

    def setUp(self):
        self.cases = evals.load_cases()

    def test_common_wordings_are_blanks(self):
        for v in ["UNKNOWN", "unknown", "Not specified", "not specified.", "TBD",
                  "TBD (not yet locked)", "To be confirmed", "N/A", "n/a", "Pending",
                  "Not stated in the request", "None", "Not specified; the email only says 'a big crowd'",
                  "TBD - confirming with journalists", ""]:
            self.assertTrue(evals.is_blank(v), v)

    def test_answers_that_mention_pending_are_not_blanks(self):
        for v in ["Cleveland (venue pending)", "Cleveland, OH", "500", "Jordan Lee",
                  "Pending Ventures Summit", "Nonestic Labs", "TBD Conference 2027"]:
            self.assertFalse(evals.is_blank(v), v)

    def test_honest_wording_is_not_fabrication(self):
        res = [evals.score_case(c, evals.mock_honest_wording(c, "")) for c in self.cases]
        s = evals.summarize(res, self.cases)
        self.assertEqual(s.fabricated, 0)
        self.assertEqual(s.recall, 1.0)
        self.assertEqual(s.blank_wording, s.unknown_total)

    def test_tbd_moderator_with_explanation_is_correct_unknown(self):
        case = next(c for c in self.cases if c.id == "10-tbd-moderator")
        out = evals.mock_faithful(case, "")
        out["moderator"] = "TBD (confirming with a few journalists)"
        f = next(f for f in evals.score_case(case, out).fields if f.field == "moderator")
        self.assertEqual(f.outcome, "correct_unknown")
        self.assertTrue(f.blank_wording)

    def test_blank_wording_on_a_known_field_is_a_miss(self):
        case = next(c for c in self.cases if c.id == "09-complete")
        out = evals.mock_faithful(case, "")
        out["date"] = "Not specified"
        f = next(f for f in evals.score_case(case, out).fields if f.field == "date")
        self.assertEqual(f.outcome, "missed")

    def test_a_guess_behind_tbd_still_trips_the_number_check(self):
        case = next(c for c in self.cases if c.id == "02-vague-crowd")
        out = evals.mock_faithful(case, "")
        out["audience_size"] = "TBD, probably around 500"
        r = evals.score_case(case, out)
        self.assertIn("500", r.invented_numbers)

    def test_faithful_drafter_has_no_wording_issues(self):
        res = [evals.score_case(c, evals.mock_faithful(c, "")) for c in self.cases]
        self.assertEqual(evals.summarize(res, self.cases).blank_wording, 0)


class PriorYearTests(unittest.TestCase):
    """v1 finding: '40,000 (based on last year's stream)' slipped past the invented-number
    check because 40,000 is in the source. It describes last year's event, not this one."""

    def setUp(self):
        self.cases = evals.load_cases()

    def test_every_case_that_mentions_last_year_is_annotated(self):
        for c in self.cases:
            if re.search(r"last year|previous year|prior year|a year ago", c.source, re.I):
                self.assertTrue(c.prior_year, f"{c.id} mentions a past event but has no prior_year")
            if c.prior_year:
                self.assertTrue(any(evals.mentions(c.source, alt) for alt in c.prior_year),
                                f"{c.id}: no prior_year figure appears in the source")

    def test_v1_virtual_failure_is_flagged(self):
        case = next(c for c in self.cases if c.id == "05-virtual")
        out = evals.mock_faithful(case, "")
        out["audience_size"] = "40,000 (based on last year's stream)"
        r = evals.score_case(case, out)
        f = next(f for f in r.fields if f.field == "audience_size")
        self.assertEqual(f.outcome, "fabricated")
        self.assertTrue(f.prior_year)
        self.assertEqual(r.invented_numbers, set())  # the old check alone misses it

    def test_figure_without_separator_or_as_k_is_flagged(self):
        case = next(c for c in self.cases if c.id == "05-virtual")
        for v in ["40000", "40K viewers"]:
            out = evals.mock_faithful(case, "")
            out["audience_size"] = v
            self.assertTrue(evals.score_case(case, out).prior_year_fields, v)

    def test_last_years_date_is_flagged(self):
        case = next(c for c in self.cases if c.id == "03-last-years-date")
        out = evals.mock_faithful(case, "")
        out["date"] = "Nov 6, 2025"
        f = next(f for f in evals.score_case(case, out).fields if f.field == "date")
        self.assertTrue(f.prior_year)

    def test_honest_blank_that_cites_last_year_is_not_flagged(self):
        case = next(c for c in self.cases if c.id == "05-virtual")
        out = evals.mock_faithful(case, "")
        out["audience_size"] = "Not specified (last year's stream reached 40,000)"
        r = evals.score_case(case, out)
        f = next(f for f in r.fields if f.field == "audience_size")
        self.assertEqual(f.outcome, "correct_unknown")
        self.assertFalse(f.prior_year)

    def test_part_of_a_larger_number_is_not_flagged(self):
        case = next(c for c in self.cases if c.id == "05-virtual")
        out = evals.mock_faithful(case, "")
        out["audience_size"] = "140,000"
        self.assertFalse(evals.score_case(case, out).prior_year_fields)

    def test_stale_drafter_is_caught_on_every_annotated_case(self):
        annotated = [c for c in self.cases if c.prior_year]
        res = [evals.score_case(c, evals.mock_stale(c, "")) for c in annotated]
        self.assertTrue(all(r.prior_year_fields for r in res))
        self.assertEqual(evals.summarize(res, annotated).invented_number_cases, 0)

    def test_faithful_drafter_has_no_prior_year_flags(self):
        res = [evals.score_case(c, evals.mock_faithful(c, "")) for c in self.cases]
        self.assertEqual(evals.summarize(res, self.cases).prior_year_fields, 0)


if __name__ == "__main__":
    unittest.main()
