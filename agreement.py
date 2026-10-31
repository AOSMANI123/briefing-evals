"""Check the answer key against independent human labels.

An eval is only as good as its answer key. This kit lets a second person label a
sample of cases without seeing the key, then measures how often you agree.

1. Make a labeling packet (sources only, no answers) and a blank sheet:
       python3 agreement.py packet --n 15 > labels/packet.md
       python3 agreement.py blank  --n 15 > labels/alex.csv
   The labeler reads packet.md and fills the `value` column: the value as the
   email states it, or UNKNOWN if the email doesn't state it for this event.

2. Export the answer key for the same sample:
       python3 agreement.py key --n 15 > labels/key.csv

3. Measure agreement:
       python3 agreement.py agree labels/key.csv labels/alex.csv

The headline number is Cohen's kappa on "stated vs. not stated", the decision that
drives the fabrication metric. It corrects for agreement you'd get by chance.
Rough reading: above 0.8 strong, 0.6 to 0.8 substantial, below 0.6 the key needs work.
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from evals import FIELDS, UNKNOWN, contains, is_blank, load_cases  # noqa: E402


def sample(n: int):
    """Deterministic, stratified: round-robin across categories so every trap type appears."""
    by_cat: dict[str, list] = {}
    for c in load_cases():
        by_cat.setdefault(c.category, []).append(c)
    picked, i = [], 0
    while len(picked) < n and any(i < len(v) for v in by_cat.values()):
        for cat in sorted(by_cat):
            if i < len(by_cat[cat]) and len(picked) < n:
                picked.append(by_cat[cat][i])
        i += 1
    return sorted(picked, key=lambda c: c.id)


def _sheet(cases, fill) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["case_id", "field", "value"])
    for c in cases:
        for f in FIELDS:
            w.writerow([c.id, f, fill(c, f)])
    return buf.getvalue()


def read_sheet(path: str) -> dict[tuple[str, str], str]:
    with open(path, newline="") as fh:
        return {(r["case_id"], r["field"]): (r["value"] or "").strip() for r in csv.DictReader(fh)}


def cohen_kappa(a: list[bool], b: list[bool]) -> float:
    n = len(a)
    if n == 0:
        raise ValueError("no items to compare")
    po = sum(x == y for x, y in zip(a, b)) / n
    pa, pb = sum(a) / n, sum(b) / n
    pe = pa * pb + (1 - pa) * (1 - pb)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def agree(path_a: str, path_b: str) -> dict:
    a, b = read_sheet(path_a), read_sheet(path_b)
    keys = sorted(set(a) & set(b))
    unlabeled = [k for k in keys if a[k] == "" or b[k] == ""]
    keys = [k for k in keys if k not in unlabeled]
    sa = [not is_blank(a[k]) for k in keys]
    sb = [not is_blank(b[k]) for k in keys]
    both = [k for k, x, y in zip(keys, sa, sb) if x and y]
    value_match = [k for k in both if contains(a[k], b[k]) or contains(b[k], a[k])]
    return {
        "items": len(keys),
        "unlabeled": len(unlabeled),
        "stated_agreement": sum(x == y for x, y in zip(sa, sb)) / len(keys) if keys else 0.0,
        "kappa": cohen_kappa(sa, sb) if keys else 0.0,
        "value_agreement": len(value_match) / len(both) if both else 1.0,
        "disagreements": [(k, a[k], b[k]) for k, x, y in zip(keys, sa, sb)
                          if x != y or (x and y and k not in value_match)],
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in ("packet", "blank", "key", "agree"):
        sys.exit(__doc__)
    cmd = argv[0]
    if cmd == "agree":
        r = agree(argv[1], argv[2])
        print(f"items compared        : {r['items']}" + (f"  ({r['unlabeled']} left blank, skipped)" if r["unlabeled"] else ""))
        print(f"stated vs. not stated : {r['stated_agreement']:.0%} agreement, Cohen's kappa {r['kappa']:.2f}")
        print(f"same value when both say stated: {r['value_agreement']:.0%}")
        if r["disagreements"]:
            print("\ndisagreements (decide each one, then fix the key or the case):")
            for (cid, f), x, y in r["disagreements"]:
                print(f"  {cid:28s} {f:15s} A={x!r}  B={y!r}")
        return r
    n = int(argv[argv.index("--n") + 1]) if "--n" in argv else 15
    cases = sample(n)
    if cmd == "packet":
        out = ["# Labeling packet", "",
               "For each email, fill in the nine fields in your CSV. Write the value as the email states it "
               "for the event being requested, or UNKNOWN if the email doesn't state it. Don't look at the answer key.",
               "", "Field meanings: see prompts/flag_gaps_v2.txt.", ""]
        for c in cases:
            out += [f"## {c.id}", "", "```", c.source, "```", ""]
        sys.stdout.write("\n".join(out))
    elif cmd == "blank":
        sys.stdout.write(_sheet(cases, lambda c, f: ""))
    else:
        sys.stdout.write(_sheet(cases, lambda c, f: c.expected[f][0] if c.expected[f] else UNKNOWN))


if __name__ == "__main__":
    main()
