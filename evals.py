"""Briefing evals: does an AI briefing drafter invent facts, or flag what it doesn't know?

Each case is a fictional engagement request plus the answer key for nine briefing
fields. Some fields are deliberately missing from the source. A good drafter fills
the known fields and returns UNKNOWN for the rest. A bad one fills the gaps with
something plausible.

Run:
    python3 evals.py --drafter mock-faithful      # harness self-check, should score 100%
    python3 evals.py --drafter mock-fabricator    # should get caught
    ANTHROPIC_API_KEY=... python3 evals.py --drafter anthropic --prompt prompts/flag_gaps.txt
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).parent
FIELDS = [
    "event_name", "date", "location", "format", "moderator",
    "audience_size", "requestor_name", "requestor_org", "ask",
]
UNKNOWN = "UNKNOWN"


# ---------- cases ----------

@dataclass
class Case:
    id: str
    trap: str
    source: str
    expected: dict  # field -> list of acceptable strings, or None if absent from source

    @classmethod
    def load(cls, path: Path) -> "Case":
        d = json.loads(path.read_text())
        exp = {}
        for f in FIELDS:
            v = d["expected"].get(f)
            exp[f] = None if v is None else (v if isinstance(v, list) else [v])
        return cls(d["id"], d["trap"], d["source"], exp)


def load_cases(folder: Path = HERE / "cases") -> list[Case]:
    return [Case.load(p) for p in sorted(folder.glob("*.json"))]


# ---------- scoring ----------

def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def numbers(s: str) -> set[str]:
    return set(re.findall(r"\d+", s.replace(",", "")))


@dataclass
class FieldResult:
    field: str
    outcome: str  # correct | missed | wrong | fabricated | correct_unknown
    got: str


@dataclass
class CaseResult:
    case_id: str
    fields: list[FieldResult]
    invented_numbers: set[str] = field(default_factory=set)

    def count(self, outcome: str) -> int:
        return sum(1 for f in self.fields if f.outcome == outcome)


def score_case(case: Case, output: dict) -> CaseResult:
    results = []
    for f in FIELDS:
        got = str(output.get(f, "") or "").strip()
        is_unknown = got.upper() == UNKNOWN or got == ""
        accepted = case.expected[f]
        if accepted is None:
            outcome = "correct_unknown" if is_unknown else "fabricated"
        elif is_unknown:
            outcome = "missed"
        elif any(norm(a) in norm(got) for a in accepted):
            outcome = "correct"
        else:
            outcome = "wrong"
        results.append(FieldResult(f, outcome, got))
    source_nums = numbers(case.source)
    out_nums = set()
    for f in FIELDS:
        v = str(output.get(f, "") or "")
        if v.upper() != UNKNOWN:
            out_nums |= numbers(v)
    return CaseResult(case.id, results, out_nums - source_nums)


@dataclass
class Summary:
    known_total: int
    known_correct: int
    unknown_total: int
    fabricated: int
    wrong: int
    missed: int
    invented_number_cases: int
    cases: int

    @property
    def recall(self) -> float:
        return self.known_correct / self.known_total if self.known_total else 0.0

    @property
    def fabrication_rate(self) -> float:
        return self.fabricated / self.unknown_total if self.unknown_total else 0.0


def summarize(results: list[CaseResult], cases: list[Case]) -> Summary:
    known_total = sum(1 for c in cases for f in FIELDS if c.expected[f] is not None)
    unknown_total = sum(1 for c in cases for f in FIELDS if c.expected[f] is None)
    return Summary(
        known_total=known_total,
        known_correct=sum(r.count("correct") for r in results),
        unknown_total=unknown_total,
        fabricated=sum(r.count("fabricated") for r in results),
        wrong=sum(r.count("wrong") for r in results),
        missed=sum(r.count("missed") for r in results),
        invented_number_cases=sum(1 for r in results if r.invented_numbers),
        cases=len(results),
    )


# ---------- drafters ----------

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


def anthropic_drafter(case: Case, prompt: str, model: str | None = None) -> dict:
    try:
        import anthropic  # pip install anthropic
    except ImportError:
        sys.exit("pip install anthropic, then set ANTHROPIC_API_KEY")
    client = anthropic.Anthropic()
    msg = client.messages.create(
        model=model or os.environ.get("EVAL_MODEL", "claude-sonnet-5"),
        max_tokens=800,
        system=prompt,
        messages=[{"role": "user", "content": case.source}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    match = re.search(r"\{.*\}", text, re.S)
    return json.loads(match.group(0)) if match else {}


DRAFTERS = {"mock-faithful": mock_faithful, "mock-fabricator": mock_fabricator,
            "anthropic": anthropic_drafter}


# ---------- cli ----------

def main(argv=None) -> Summary:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--drafter", choices=DRAFTERS, default="mock-faithful")
    ap.add_argument("--prompt", default=str(HERE / "prompts" / "flag_gaps.txt"))
    ap.add_argument("--out", help="write per-field results to this JSON file")
    args = ap.parse_args(argv)

    prompt = Path(args.prompt).read_text()
    cases = load_cases()
    drafter = DRAFTERS[args.drafter]
    results = [score_case(c, drafter(c, prompt)) for c in cases]
    s = summarize(results, cases)

    print(f"drafter: {args.drafter}   prompt: {Path(args.prompt).name}   cases: {s.cases}")
    print(f"recall on known fields : {s.known_correct}/{s.known_total} ({s.recall:.0%})")
    print(f"fabrication rate       : {s.fabricated}/{s.unknown_total} missing fields filled in ({s.fabrication_rate:.0%})")
    print(f"wrong values           : {s.wrong}")
    print(f"missed (said UNKNOWN)  : {s.missed}")
    print(f"cases with a number not in the source: {s.invented_number_cases}")
    for r in results:
        bad = [f"{f.field}={f.got!r}" for f in r.fields if f.outcome in ("fabricated", "wrong")]
        if bad:
            print(f"  {r.case_id}: " + "; ".join(bad))
    if args.out:
        Path(args.out).write_text(json.dumps(
            [{"case": r.case_id, "fields": [f.__dict__ for f in r.fields],
              "invented_numbers": sorted(r.invented_numbers)} for r in results], indent=2))
    return s


if __name__ == "__main__":
    main()
