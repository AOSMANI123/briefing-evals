"""Checks that the scorer rewards a faithful drafter and catches a fabricating one.
Run: python3 -m unittest discover -s tests
"""
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


if __name__ == "__main__":
    unittest.main()
