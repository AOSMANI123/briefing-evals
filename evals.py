"""Briefing evals: does an AI briefing drafter invent facts, or flag what it doesn't know?

Each case is a fictional engagement request plus the answer key for nine briefing
fields. Some fields are deliberately missing from the source. A good drafter fills
the known fields and returns UNKNOWN for the rest. A bad one fills the gaps with
something plausible.

Run a suite (N repeated runs per prompt):
    python3 evals.py --drafter mock-faithful                     # self-check, should score 100%
    python3 evals.py --drafter mock-noisy --runs 10 --out runs/noisy.json
    python3 evals.py --drafter anthropic --model <model-id> --prompt prompts/flag_gaps.txt \\
        --runs 10 --out runs/claude-flag_gaps.json

Compare two saved runs and apply the pass gate:
    python3 evals.py compare runs/baseline.json runs/candidate.json

Estimate the gate's false-positive rate from one N-run file:
    python3 evals.py calibrate runs/baseline.json

Table of several saved runs (for the readiness memo):
    python3 evals.py table runs/*.json
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent
FIELDS = [
    "event_name", "date", "location", "format", "moderator",
    "audience_size", "requestor_name", "requestor_org", "ask",
]
UNKNOWN = "UNKNOWN"
CATEGORIES = {
    "control", "missing_field", "vague_quantity", "stale_info", "pending_info",
    "attribution", "role_confusion", "distractor_event", "precision", "correction",
}

# Phrases that mean "the source doesn't say". v1 counted only the literal UNKNOWN,
# which scored honest answers like "TBD" or "Not specified" as fabrications.
HONEST_BLANK = re.compile(
    r"^(unknown|n/?a|none|null|not (specified|stated|provided|mentioned|given|listed|confirmed)"
    r"|tbd|tbc|tba|to be (determined|confirmed|announced|decided)|pending|unspecified|unclear)\.?$"
)


# ---------- cases ----------

@dataclass
class Case:
    id: str
    category: str
    trap: str
    source: str
    expected: dict          # field -> list of acceptable strings, or None if absent from source
    forbidden: dict = field(default_factory=dict)  # field -> strings from the source that must not land there

    @classmethod
    def load(cls, path: Path) -> "Case":
        d = json.loads(path.read_text())
        exp = {}
        for f in FIELDS:
            v = d["expected"].get(f)
            exp[f] = None if v is None else (v if isinstance(v, list) else [v])
        return cls(d["id"], d.get("category", "uncategorized"), d["trap"], d["source"], exp,
                   d.get("forbidden", {}))


def load_cases(folder: Path = HERE / "cases") -> list[Case]:
    return [Case.load(p) for p in sorted(folder.glob("*.json"))]


# ---------- scoring ----------

def norm(s: str) -> str:
    s = re.sub(r"(?<=\d),(?=\d{3}\b)", "", s.lower())  # "1,200" and "1200" are the same number
    s = re.sub(r"[^a-z0-9]+", " ", s).strip()
    return re.sub(r"\b(minute|hour)s\b", r"\1", s)        # "30 minutes" matches "30-minute"


def numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+", s.replace(",", "")))


def is_blank(got: str) -> bool:
    """True if the drafter declined to answer, in any common wording.

    A trailing parenthetical is ignored, so "TBD (not yet locked)" is a blank,
    but "Chicago (venue TBD)" is not: the part outside the parentheses is a value.
    """
    core = re.sub(r"\s*\(.*\)\s*$", "", got.strip()).strip().lower()
    return core == "" or bool(HONEST_BLANK.match(core))


def contains(haystack: str, needle: str) -> bool:
    n = norm(needle)
    return bool(n) and re.search(rf"(^| ){re.escape(n)}( |$)", norm(haystack)) is not None


@dataclass
class FieldResult:
    field: str
    outcome: str  # correct | missed | wrong | fabricated | correct_unknown
    got: str
    carried_over: bool = False   # contains a value the source ties to a different event/role/time
    blank_wording: bool = False  # an honest blank, but not written as the literal UNKNOWN


@dataclass
class CaseResult:
    case_id: str
    fields: list[FieldResult]
    invented_numbers: set[str] = field(default_factory=set)
    parse_error: bool = False

    def count(self, outcome: str) -> int:
        return sum(1 for f in self.fields if f.outcome == outcome)


def score_case(case: Case, output: dict | None) -> CaseResult:
    parse_error = not isinstance(output, dict) or not output
    output = output if isinstance(output, dict) else {}
    results = []
    for f in FIELDS:
        got = str(output.get(f, "") or "").strip()
        blank = is_blank(got)
        accepted = case.expected[f]
        if accepted is None:
            outcome = "correct_unknown" if blank else "fabricated"
        elif blank:
            outcome = "missed"
        elif any(contains(got, a) for a in accepted):
            outcome = "correct"
        else:
            outcome = "wrong"
        # A forbidden value next to the right one is context ("May 13, moved from May 6"),
        # not an error. It only counts when the field is otherwise wrong or invented.
        carried = (not blank and outcome != "correct"
                   and any(contains(got, v) for v in case.forbidden.get(f, [])))
        results.append(FieldResult(f, outcome, got, carried,
                                   blank and got.strip().upper() != UNKNOWN and got != ""))
    source_nums = numbers(case.source)
    out_nums = set()
    for f in FIELDS:
        v = str(output.get(f, "") or "")
        if not is_blank(v):
            out_nums |= numbers(v)
    return CaseResult(case.id, results, out_nums - source_nums, parse_error)


@dataclass
class Summary:
    known_total: int
    known_correct: int
    unknown_total: int
    fabricated: int
    wrong: int
    missed: int
    carried_over: int
    invented_number_cases: int
    blank_wording: int
    parse_errors: int
    cases: int

    @property
    def recall(self) -> float:
        return self.known_correct / self.known_total if self.known_total else 0.0

    @property
    def fabrication_rate(self) -> float:
        return self.fabricated / self.unknown_total if self.unknown_total else 0.0


def summarize(results: list[CaseResult], cases: list[Case]) -> Summary:
    ids = {r.case_id for r in results}
    cases = [c for c in cases if c.id in ids]
    return Summary(
        known_total=sum(1 for c in cases for f in FIELDS if c.expected[f] is not None),
        known_correct=sum(r.count("correct") for r in results),
        unknown_total=sum(1 for c in cases for f in FIELDS if c.expected[f] is None),
        fabricated=sum(r.count("fabricated") for r in results),
        wrong=sum(r.count("wrong") for r in results),
        missed=sum(r.count("missed") for r in results),
        carried_over=sum(1 for r in results for f in r.fields if f.carried_over),
        invented_number_cases=sum(1 for r in results if r.invented_numbers),
        blank_wording=sum(1 for r in results for f in r.fields if f.blank_wording),
        parse_errors=sum(1 for r in results if r.parse_error),
        cases=len(results),
    )


# ---------- drafters ----------
# Each drafter returns (output_dict, usage). usage has input_tokens, output_tokens, seconds.

def mock_faithful(case: Case, prompt: str) -> dict:
    """Uses the answer key. Exists only to prove the scorer gives a perfect drafter 100%."""
    return {f: (case.expected[f][0] if case.expected[f] else UNKNOWN) for f in FIELDS}


PLAUSIBLE = {
    "event_name": "Annual Leadership Summit", "date": "October 1, 2026",
    "location": "New York, NY", "format": "Fireside chat", "moderator": "Jordan Lee",
    "audience_size": "500", "requestor_name": "Sam Rivera",
    "requestor_org": "Contoso", "ask": "Keynote remarks",
}


def mock_fabricator(case: Case, prompt: str) -> dict:
    """Fills every gap with something plausible. The scorer should catch every one."""
    return {f: (case.expected[f][0] if case.expected[f] else PLAUSIBLE[f]) for f in FIELDS}


def mock_noisy(case: Case, prompt: str, run: int = 0, p_fab: float = 0.10, p_miss: float = 0.04) -> dict:
    """A simulated imperfect model: mostly faithful, sometimes fills a gap or drops a fact.
    Seeded by case and run, so results are repeatable. Used to test the gate offline.
    It is a simulation, not a model, and its numbers say nothing about any real model."""
    rng = random.Random(f"{case.id}:{run}:{p_fab}:{p_miss}")
    out = {}
    for f in FIELDS:
        if case.expected[f] is None:
            out[f] = PLAUSIBLE[f] if rng.random() < p_fab else UNKNOWN
        else:
            out[f] = UNKNOWN if rng.random() < p_miss else case.expected[f][0]
    return out


def _json_from(text: str) -> dict:
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return {}


def anthropic_drafter(case: Case, prompt: str, model: str) -> tuple[dict, dict]:
    try:
        import anthropic  # pip install anthropic
    except ImportError:
        sys.exit("pip install anthropic, then set ANTHROPIC_API_KEY")
    t = time.monotonic()
    msg = anthropic.Anthropic().messages.create(
        model=model, max_tokens=800, system=prompt,
        messages=[{"role": "user", "content": case.source}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    return _json_from(text), {"input_tokens": msg.usage.input_tokens,
                              "output_tokens": msg.usage.output_tokens,
                              "seconds": time.monotonic() - t}


def openai_drafter(case: Case, prompt: str, model: str) -> tuple[dict, dict]:
    try:
        from openai import OpenAI  # pip install openai
    except ImportError:
        sys.exit("pip install openai, then set OPENAI_API_KEY")
    t = time.monotonic()
    r = OpenAI().chat.completions.create(
        model=model,
        messages=[{"role": "system", "content": prompt}, {"role": "user", "content": case.source}],
    )
    return _json_from(r.choices[0].message.content), {
        "input_tokens": r.usage.prompt_tokens, "output_tokens": r.usage.completion_tokens,
        "seconds": time.monotonic() - t}


def google_drafter(case: Case, prompt: str, model: str) -> tuple[dict, dict]:
    try:
        from google import genai  # pip install google-genai
    except ImportError:
        sys.exit("pip install google-genai, then set GEMINI_API_KEY")
    t = time.monotonic()
    r = genai.Client().models.generate_content(
        model=model, contents=case.source, config={"system_instruction": prompt})
    u = r.usage_metadata
    return _json_from(r.text), {"input_tokens": u.prompt_token_count or 0,
                                "output_tokens": u.candidates_token_count or 0,
                                "seconds": time.monotonic() - t}


MOCKS = {"mock-faithful": mock_faithful, "mock-fabricator": mock_fabricator, "mock-noisy": mock_noisy}
APIS = {"anthropic": anthropic_drafter, "openai": openai_drafter, "google": google_drafter}
DRAFTERS = {**MOCKS, **APIS}


def call_drafter(name: str, case: Case, prompt: str, model: str | None, run: int) -> tuple[dict, dict]:
    if name in APIS:
        if not model:
            sys.exit(f"--model is required for the {name} drafter (use the provider's exact model ID)")
        return APIS[name](case, prompt, model)
    fn = MOCKS[name]
    out = fn(case, prompt, run) if name == "mock-noisy" else fn(case, prompt)
    return out, {"input_tokens": 0, "output_tokens": 0, "seconds": 0.0}


# ---------- suites of repeated runs ----------

def run_suite(drafter: str, prompt_path: str, model: str | None = None, runs: int = 1,
              cases: list[Case] | None = None, price_in: float | None = None,
              price_out: float | None = None) -> dict:
    """Run every case `runs` times. Returns a JSON-serializable record."""
    cases = cases if cases is not None else load_cases()
    prompt = Path(prompt_path).read_text()
    record = {"drafter": drafter, "model": model or drafter, "prompt": Path(prompt_path).name,
              "cases": len(cases), "runs": []}
    for i in range(runs):
        results, usage = [], {"input_tokens": 0, "output_tokens": 0, "seconds": []}
        for c in cases:
            out, u = call_drafter(drafter, c, prompt, model, i)
            results.append(score_case(c, out))
            usage["input_tokens"] += u["input_tokens"]
            usage["output_tokens"] += u["output_tokens"]
            usage["seconds"].append(u["seconds"])
        s = summarize(results, cases)
        cost = None
        if price_in is not None and price_out is not None:
            cost = (usage["input_tokens"] * price_in + usage["output_tokens"] * price_out) / 1_000_000
        record["runs"].append({
            "summary": {**s.__dict__, "recall": s.recall, "fabrication_rate": s.fabrication_rate},
            "usage": {"input_tokens": usage["input_tokens"], "output_tokens": usage["output_tokens"],
                      "median_seconds_per_case": statistics.median(usage["seconds"]) if usage["seconds"] else 0,
                      "cost_usd": cost},
            "results": [{"case": r.case_id, "invented_numbers": sorted(r.invented_numbers),
                         "parse_error": r.parse_error, "fields": [f.__dict__ for f in r.fields]}
                        for r in results],
        })
    return record


def _metric(record: dict, key: str) -> list[float]:
    return [r["summary"][key] for r in record["runs"]]


def _failure_rates(record: dict) -> dict[tuple[str, str], float]:
    """Share of runs in which each (case, field) failed (fabricated, wrong or missed)."""
    n = len(record["runs"])
    counts: dict[tuple[str, str], int] = {}
    for run in record["runs"]:
        for r in run["results"]:
            for f in r["fields"]:
                if f["outcome"] in ("fabricated", "wrong", "missed"):
                    k = (r["case"], f["field"])
                    counts[k] = counts.get(k, 0) + 1
    return {k: v / n for k, v in counts.items()}


# ---------- pass gate (ADR-002) ----------

GATED = [  # metric, direction a regression moves in
    ("fabricated", +1), ("carried_over", +1), ("invented_number_cases", +1),
    ("known_correct", -1), ("parse_errors", +1),
]


GATE_Z = 2.5  # one-sided; about a 0.6% chance per metric of failing an unchanged prompt


def gate(baseline: dict, candidate: dict, z: float = GATE_Z) -> tuple[bool, list[str]]:
    """Fail the candidate if any gated metric moves the wrong way by more than run-to-run
    noise explains. Noise is the baseline's standard deviation across its runs, scaled by
    how many runs each side has: allowed = z * sd * sqrt(1/n_baseline + 1/n_candidate).
    More runs on either side shrink the allowance, so the gate gets sharper with evidence.
    With fewer than 2 baseline runs there is no noise estimate, so any regression fails."""
    reasons = []
    nb, nc = len(baseline["runs"]), len(candidate["runs"])
    for key, direction in GATED:
        b, c = _metric(baseline, key), _metric(candidate, key)
        sd = statistics.stdev(b) if nb >= 2 else 0.0
        allowed = z * sd * (1 / nb + 1 / nc) ** 0.5
        delta = (statistics.mean(c) - statistics.mean(b)) * direction
        if delta > allowed and delta > 0:
            reasons.append(f"{key}: {statistics.mean(b):.1f} -> {statistics.mean(c):.1f} "
                           f"(noise allows {allowed:.1f})")
    return not reasons, reasons


def classify_failures(baseline: dict, candidate: dict, threshold: float = 0.5) -> dict[str, list]:
    """Sort each failing (case, field) by what would fix it.

    fixed_by_candidate : failed in most baseline runs, never in the candidate -> prompt-fixable
    persistent         : fails in most runs of both -> look at the schema, answer key or model
    introduced         : never failed in baseline, fails in most candidate runs -> regression
    flaky              : fails in some runs but not most -> nondeterminism; needs more runs
    """
    b, c = _failure_rates(baseline), _failure_rates(candidate)
    out = {"fixed_by_candidate": [], "persistent": [], "introduced": [], "flaky": []}
    for k in sorted(set(b) | set(c)):
        rb, rc = b.get(k, 0.0), c.get(k, 0.0)
        if rb >= threshold and rc == 0:
            out["fixed_by_candidate"].append((*k, rb, rc))
        elif rb >= threshold and rc >= threshold:
            out["persistent"].append((*k, rb, rc))
        elif rb == 0 and rc >= threshold:
            out["introduced"].append((*k, rb, rc))
        else:
            out["flaky"].append((*k, rb, rc))
    return out


def calibrate(record: dict) -> tuple[float, list[bool]]:
    """Leave-one-out false-positive estimate: treat each run as a 'candidate' against the
    other runs of the same, unchanged prompt. Any failure is a false positive."""
    runs = record["runs"]
    if len(runs) < 3:
        sys.exit("calibrate needs at least 3 runs of the same prompt (use --runs)")
    fails = []
    for i in range(len(runs)):
        base = {**record, "runs": runs[:i] + runs[i + 1:]}
        cand = {**record, "runs": [runs[i]]}
        fails.append(not gate(base, cand)[0])
    return sum(fails) / len(fails), fails


# ---------- printing ----------

def _mean_range(xs: list[float], pct: bool = False) -> str:
    m = statistics.mean(xs)
    if pct:
        return f"{m:.0%}" if len(xs) == 1 else f"{m:.0%} ({min(xs):.0%}-{max(xs):.0%})"
    return f"{m:.1f}" if len(xs) == 1 else f"{m:.1f} ({min(xs):g}-{max(xs):g})"


def print_suite(record: dict, cases: list[Case]) -> None:
    last = record["runs"][-1]["summary"]
    n = len(record["runs"])
    print(f"drafter: {record['drafter']}   model: {record['model']}   prompt: {record['prompt']}   "
          f"cases: {record['cases']}   runs: {n}")
    print(f"recall on known fields  : {_mean_range(_metric(record, 'recall'), True)} of {last['known_total']}")
    print(f"fabrication rate        : {_mean_range(_metric(record, 'fabrication_rate'), True)} of {last['unknown_total']} missing fields")
    print(f"fabricated fields       : {_mean_range(_metric(record, 'fabricated'))}")
    print(f"wrong values            : {_mean_range(_metric(record, 'wrong'))}")
    print(f"missed (said blank)     : {_mean_range(_metric(record, 'missed'))}")
    print(f"carried-over values     : {_mean_range(_metric(record, 'carried_over'))}")
    print(f"cases w/ invented number: {_mean_range(_metric(record, 'invented_number_cases'))}")
    print(f"blanks not worded UNKNOWN: {_mean_range(_metric(record, 'blank_wording'))}  (scored as blanks, not fabrications)")
    if any(r["usage"]["input_tokens"] for r in record["runs"]):
        u = record["runs"]
        print(f"tokens per run          : {statistics.mean(r['usage']['input_tokens'] for r in u):.0f} in / "
              f"{statistics.mean(r['usage']['output_tokens'] for r in u):.0f} out; "
              f"median {statistics.median(r['usage']['median_seconds_per_case'] for r in u):.1f}s per case")
        costs = [r["usage"]["cost_usd"] for r in u if r["usage"]["cost_usd"] is not None]
        if costs:
            print(f"cost per run            : ${statistics.mean(costs):.4f}")
    cat = {c.id: c.category for c in cases}
    rates = _failure_rates(record)
    if rates:
        print("\nfailures (share of runs):")
        for (cid, f), r in sorted(rates.items(), key=lambda kv: (-kv[1], kv[0])):
            got = next(x["got"] for run in record["runs"] for res in run["results"] if res["case"] == cid
                       for x in res["fields"] if x["field"] == f and x["outcome"] != "correct"
                       and x["outcome"] != "correct_unknown")
            print(f"  {r:4.0%}  {cid:28s} [{cat.get(cid, '?')}] {f} = {got!r}")


def print_compare(base: dict, cand: dict, cases: list[Case]) -> bool:
    ok, reasons = gate(base, cand)
    nb, nc = len(base["runs"]), len(cand["runs"])
    print(f"baseline : {base['model']} / {base['prompt']} ({nb} runs)")
    print(f"candidate: {cand['model']} / {cand['prompt']} ({nc} runs)")
    if nb < 3:
        print("note: baseline has fewer than 3 runs, so the noise estimate is weak or missing (uncalibrated)")
    for key, _ in GATED:
        print(f"  {key:22s} {_mean_range(_metric(base, key)):>16s} -> {_mean_range(_metric(cand, key))}")
    print("\nGATE:", "PASS" if ok else "FAIL")
    for r in reasons:
        print("  -", r)
    cat = {c.id: c.category for c in cases}
    groups = classify_failures(base, cand)
    labels = {"fixed_by_candidate": "Fixed by the candidate (prompt-fixable)",
              "persistent": "Persistent under both (check the schema, answer key or model)",
              "introduced": "Introduced by the candidate (regression)",
              "flaky": "Flaky (fails in some runs; needs more runs to call)"}
    for g, rows in groups.items():
        if rows:
            print(f"\n{labels[g]}:")
            for cid, f, rb, rc in rows:
                print(f"  {cid:28s} [{cat.get(cid, '?')}] {f:15s} {rb:4.0%} -> {rc:4.0%}")
    return ok


def print_table(records: list[dict]) -> None:
    print("| Model | Prompt | Runs | Recall | Fabrication rate | Carried over | Invented numbers | Cost per run | Median s/case |")
    print("|---|---|---|---|---|---|---|---|---|")
    for rec in records:
        u = rec["runs"]
        costs = [r["usage"]["cost_usd"] for r in u if r["usage"]["cost_usd"] is not None]
        cost = f"${statistics.mean(costs):.4f}" if costs else "n/a"
        secs = statistics.median(r["usage"]["median_seconds_per_case"] for r in u)
        print(f"| {rec['model']} | {rec['prompt']} | {len(u)} | {_mean_range(_metric(rec, 'recall'), True)} | "
              f"{_mean_range(_metric(rec, 'fabrication_rate'), True)} | {_mean_range(_metric(rec, 'carried_over'))} | "
              f"{_mean_range(_metric(rec, 'invented_number_cases'))} | {cost} | {secs:.1f} |")


# ---------- cli ----------

def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    cases = load_cases()
    if argv and argv[0] in ("compare", "calibrate", "table"):
        cmd, files = argv[0], argv[1:]
        recs = [json.loads(Path(f).read_text()) for f in files]
        if cmd == "compare":
            if len(recs) != 2:
                sys.exit("usage: evals.py compare BASELINE.json CANDIDATE.json")
            ok = print_compare(recs[0], recs[1], cases)
            sys.exit(0 if ok else 1)
        if cmd == "calibrate":
            if len(recs) != 1:
                sys.exit("usage: evals.py calibrate RUNS.json")
            rate, fails = calibrate(recs[0])
            print(f"{recs[0]['model']} / {recs[0]['prompt']}: {len(fails)} runs, "
                  f"gate fails an unchanged prompt in {sum(fails)} of {len(fails)} leave-one-out checks "
                  f"({rate:.0%} false-positive rate; target < 5%)")
            return rate
        print_table(recs)
        return recs

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafter", choices=DRAFTERS, default="mock-faithful")
    ap.add_argument("--model", help="exact model ID (required for anthropic, openai, google)")
    ap.add_argument("--prompt", default=str(HERE / "prompts" / "flag_gaps.txt"))
    ap.add_argument("--runs", type=int, default=1, help="repeat the whole suite N times")
    ap.add_argument("--category", help="only run cases in this category")
    ap.add_argument("--price-in", type=float, help="USD per million input tokens, from the provider's pricing page")
    ap.add_argument("--price-out", type=float, help="USD per million output tokens")
    ap.add_argument("--out", help="write the full run record to this JSON file")
    args = ap.parse_args(argv)
    if args.category:
        cases = [c for c in cases if c.category == args.category]
    record = run_suite(args.drafter, args.prompt, args.model, args.runs, cases, args.price_in, args.price_out)
    if args.out:  # save before printing, so a closed pipe can't lose a paid-for run
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(json.dumps(record, indent=1))
    print_suite(record, cases)
    s = record["runs"][-1]["summary"]
    return Summary(**{k: v for k, v in s.items() if k in Summary.__dataclass_fields__})


if __name__ == "__main__":
    main()
