"""Checks the scorer, the answer key, the pass gate and the agreement math.
Run: python3 -m unittest discover -s tests
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agreement  # noqa: E402
import evals  # noqa: E402

HERE = Path(__file__).resolve().parents[1]


def field(result, name):
    return next(f for f in result.fields if f.field == name)


class CaseLibraryTests(unittest.TestCase):
    """The answer key checks itself, so a typo in a case can't silently skew results."""

    def setUp(self):
        self.cases = evals.load_cases()

    def test_fifty_unique_cases_with_known_categories(self):
        self.assertEqual(len(self.cases), 50)
        self.assertEqual(len({c.id for c in self.cases}), 50)
        for c in self.cases:
            self.assertIn(c.category, evals.CATEGORIES, c.id)
        cats = {c.category for c in self.cases}
        self.assertEqual(cats, evals.CATEGORIES)

    def test_controls_are_complete(self):
        controls = [c for c in self.cases if c.category == "control"]
        self.assertGreaterEqual(len(controls), 3)
        for c in controls:
            self.assertTrue(all(c.expected[f] is not None for f in evals.FIELDS), c.id)

    def test_enough_gaps(self):
        gaps = sum(1 for c in self.cases for f in evals.FIELDS if c.expected[f] is None)
        self.assertGreaterEqual(gaps, 40)

    def test_stated_values_appear_in_the_source(self):
        # format and ask can be paraphrased; every other stated value must be findable.
        for c in self.cases:
            for f in evals.FIELDS:
                if c.expected[f] is None or f in ("format", "ask"):
                    continue
                self.assertTrue(any(evals.contains(c.source, a) for a in c.expected[f]),
                                f"{c.id}.{f}: none of {c.expected[f]} found in source")

    def test_forbidden_values_come_from_the_source(self):
        for c in self.cases:
            for f, vals in c.forbidden.items():
                self.assertIn(f, evals.FIELDS, c.id)
                for v in vals:
                    self.assertTrue(evals.contains(c.source, v), f"{c.id}.{f}: {v!r} not in source")

    def test_forbidden_values_are_never_accepted_answers(self):
        for c in self.cases:
            for f, vals in c.forbidden.items():
                for v in vals:
                    for a in c.expected[f] or []:
                        self.assertFalse(evals.contains(a, v), f"{c.id}.{f}: {v!r} overlaps answer {a!r}")


class ScorerTests(unittest.TestCase):
    def setUp(self):
        self.cases = evals.load_cases()
        self.by_id = {c.id: c for c in self.cases}

    def test_faithful_drafter_scores_perfectly(self):
        res = [evals.score_case(c, evals.mock_faithful(c, "")) for c in self.cases]
        s = evals.summarize(res, self.cases)
        self.assertEqual(s.recall, 1.0)
        self.assertEqual((s.fabricated, s.wrong, s.carried_over, s.invented_number_cases), (0, 0, 0, 0))

    def test_fabricator_is_caught_on_every_gap(self):
        res = [evals.score_case(c, evals.mock_fabricator(c, "")) for c in self.cases]
        s = evals.summarize(res, self.cases)
        self.assertEqual(s.fabricated, s.unknown_total)
        self.assertGreater(s.invented_number_cases, 0)

    def test_honest_blanks_in_any_wording_are_not_fabrications(self):
        case = self.by_id["01-no-moderator"]
        for blank in ["UNKNOWN", "unknown", "Not specified", "TBD", "TBD (not yet locked)",
                      "N/A", "Not stated.", "To be confirmed", ""]:
            out = evals.mock_faithful(case, "")
            out["moderator"] = blank
            self.assertEqual(field(evals.score_case(case, out), "moderator").outcome,
                             "correct_unknown", blank)

    def test_value_with_parenthetical_is_not_a_blank(self):
        self.assertFalse(evals.is_blank("Chicago (venue TBD)"))
        self.assertTrue(evals.is_blank("TBD (venue pending)"))

    def test_blank_wording_is_counted_separately(self):
        case = self.by_id["01-no-moderator"]
        out = evals.mock_faithful(case, "")
        out["moderator"] = "Not specified"
        r = evals.score_case(case, out)
        self.assertTrue(field(r, "moderator").blank_wording)

    def test_last_years_audience_is_carried_over(self):
        # v1 missed this: 40,000 is in the source, but about last year's stream.
        case = self.by_id["05-virtual"]
        out = evals.mock_faithful(case, "")
        out["audience_size"] = "40,000 (based on last year's stream)"
        r = evals.score_case(case, out)
        self.assertEqual(field(r, "audience_size").outcome, "fabricated")
        self.assertTrue(field(r, "audience_size").carried_over)
        self.assertEqual(r.invented_numbers, set())  # the number check alone can't see it

    def test_right_value_with_old_value_as_context_is_correct(self):
        case = self.by_id["48-date-moved"]
        out = evals.mock_faithful(case, "")
        out["date"] = "May 13, 2027 (moved from May 6)"
        r = field(evals.score_case(case, out), "date")
        self.assertEqual((r.outcome, r.carried_over), ("correct", False))

    def test_old_value_alone_is_carried_over(self):
        case = self.by_id["48-date-moved"]
        out = evals.mock_faithful(case, "")
        out["date"] = "May 6, 2027"
        r = field(evals.score_case(case, out), "date")
        self.assertEqual((r.outcome, r.carried_over), ("wrong", True))

    def test_hyphenated_duration_matches(self):
        case = self.by_id["28-stale-format"]
        out = evals.mock_faithful(case, "")
        out["ask"] = "A 30-minute slot on the program"
        self.assertEqual(field(evals.score_case(case, out), "ask").outcome, "correct")

    def test_introducer_is_not_the_moderator(self):
        for cid, name in [("02-vague-crowd", "Priya Nand"), ("09-introducer", "Maria Gonzalez"),
                          ("40-keynote-introducer", "Sam Arden")]:
            case = self.by_id[cid]
            out = evals.mock_faithful(case, "")
            out["moderator"] = name
            r = field(evals.score_case(case, out), "moderator")
            self.assertEqual(r.outcome, "fabricated", cid)
            self.assertTrue(r.carried_over, cid)

    def test_last_years_date_counts_as_fabrication(self):
        case = self.by_id["03-last-years-date"]
        out = evals.mock_faithful(case, "")
        out["date"] = "November 6, 2025"
        self.assertEqual(field(evals.score_case(case, out), "date").outcome, "fabricated")

    def test_rounded_range_is_wrong(self):
        case = self.by_id["07-range"]
        out = evals.mock_faithful(case, "")
        out["audience_size"] = "275"
        r = evals.score_case(case, out)
        self.assertEqual(field(r, "audience_size").outcome, "wrong")
        self.assertIn("275", r.invented_numbers)

    def test_numbers_match_whole_words_only(self):
        case = self.by_id["01-no-moderator"]  # audience 600
        out = evals.mock_faithful(case, "")
        out["audience_size"] = "6000"
        self.assertEqual(field(evals.score_case(case, out), "audience_size").outcome, "wrong")

    def test_forwarder_is_not_the_requestor(self):
        case = self.by_id["04-forwarded"]
        out = evals.mock_faithful(case, "")
        out["requestor_name"] = "Chris"
        r = field(evals.score_case(case, out), "requestor_name")
        self.assertEqual(r.outcome, "wrong")
        self.assertTrue(r.carried_over)

    def test_multiday_range_is_not_the_ask_day(self):
        case = self.by_id["46-multiday-event"]
        out = evals.mock_faithful(case, "")
        out["date"] = "June 14-16, 2027"
        self.assertEqual(field(evals.score_case(case, out), "date").outcome, "wrong")

    def test_unparseable_output_is_flagged(self):
        r = evals.score_case(self.cases[0], {})
        self.assertTrue(r.parse_error)


class GateTests(unittest.TestCase):
    def setUp(self):
        self.prompt = str(HERE / "prompts" / "flag_gaps_v2.txt")

    def suite(self, drafter, runs=1):
        return evals.run_suite(drafter, self.prompt, runs=runs)

    def test_gate_passes_identical_runs(self):
        ok, _ = evals.gate(self.suite("mock-faithful"), self.suite("mock-faithful"))
        self.assertTrue(ok)

    def test_gate_fails_a_fabricating_candidate(self):
        ok, reasons = evals.gate(self.suite("mock-faithful"), self.suite("mock-fabricator"))
        self.assertFalse(ok)
        self.assertTrue(any(r.startswith("fabricated") for r in reasons))

    def test_gate_fails_a_fabricator_even_against_a_noisy_baseline(self):
        ok, _ = evals.gate(self.suite("mock-noisy", runs=10), self.suite("mock-fabricator"))
        self.assertFalse(ok)

    def test_calibration_on_simulated_noise_is_under_target(self):
        rate, fails = evals.calibrate(self.suite("mock-noisy", runs=20))
        self.assertEqual(len(fails), 20)
        self.assertLessEqual(rate, 0.10)  # leave-one-out on a simulated model; real target is < 5%

    def test_noisy_drafter_is_repeatable(self):
        a, b = self.suite("mock-noisy", runs=3), self.suite("mock-noisy", runs=3)
        self.assertEqual(evals._metric(a, "fabricated"), evals._metric(b, "fabricated"))

    def test_classify_failures(self):
        base = self.suite("mock-fabricator", runs=2)
        cand = self.suite("mock-faithful", runs=2)
        groups = evals.classify_failures(base, cand)
        self.assertTrue(groups["fixed_by_candidate"])
        self.assertFalse(groups["introduced"])
        groups = evals.classify_failures(cand, base)
        self.assertTrue(groups["introduced"])

    def test_api_drafters_require_a_model(self):
        with self.assertRaises(SystemExit):
            evals.call_drafter("anthropic", evals.load_cases()[0], "", None, 0)

    def test_cost_is_computed_only_when_prices_are_given(self):
        rec = evals.run_suite("mock-faithful", self.prompt)
        self.assertIsNone(rec["runs"][0]["usage"]["cost_usd"])


class AgreementTests(unittest.TestCase):
    def test_kappa_known_values(self):
        self.assertEqual(agreement.cohen_kappa([True, False] * 5, [True, False] * 5), 1.0)
        # 20 items: both yes 8, both no 6, A-only 4, B-only 2 -> po .70, pe .50, kappa .40
        a = [True] * 8 + [False] * 6 + [True] * 4 + [False] * 2
        b = [True] * 8 + [False] * 6 + [False] * 4 + [True] * 2
        self.assertAlmostEqual(agreement.cohen_kappa(a, b), 0.40, places=2)

    def test_sample_covers_every_category(self):
        cats = {c.category for c in agreement.sample(15)}
        self.assertEqual(cats, evals.CATEGORIES)

    def test_key_agrees_with_itself_and_flags_a_changed_label(self):
        cases = agreement.sample(15)
        with tempfile.TemporaryDirectory() as d:
            key = Path(d) / "key.csv"
            key.write_text(agreement._sheet(cases, lambda c, f: c.expected[f][0] if c.expected[f] else "UNKNOWN"))
            r = agreement.agree(str(key), str(key))
            self.assertEqual((r["kappa"], r["value_agreement"], r["disagreements"]), (1.0, 1.0, []))
            with key.open(newline="") as fh:
                rows = list(csv.reader(fh))
            i = next(i for i, row in enumerate(rows) if row[1] == "moderator" and row[2] == "UNKNOWN")
            rows[i][2] = "Somebody"
            other = Path(d) / "other.csv"
            with other.open("w", newline="") as fh:
                csv.writer(fh).writerows(rows)
            r = agreement.agree(str(key), str(other))
            self.assertLess(r["kappa"], 1.0)
            self.assertEqual(len(r["disagreements"]), 1)


if __name__ == "__main__":
    unittest.main()
