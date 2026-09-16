"""Offline check: runs the whole pipeline on invented papers.

    python -m digest.selftest

Touches no network and costs nothing. It proves the roster loads, that papers
are attributed to the right people, and that the email renders. It cannot tell
you whether OpenAlex has the right data - only a real run does that.
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from . import render, roster
from .config import ROOT, Config
from .openalex import Work
from .state import SeenWorks

SAMPLE_ROSTER = """name,openalex_author_id,department,active,notes
Ada Lovelace,A5000000001,Computer Science and Applied Mathematics,yes,
Rosalind Franklin,,Structural Biology,yes,matched by name only
Dorothy Hodgkin,A5000000003,Chemical and Biological Physics,yes,
Retired Person,A5000000004,Physics,no,should be ignored
"""


def _work(wid, title, authors, journal="Nature", preprint=False, day="2026-09-14"):
    return Work(
        id=f"https://openalex.org/{wid}", title=title, doi=None,
        url=f"https://doi.org/10.1234/{wid}", published=day, year=2026,
        work_type="preprint" if preprint else "article", journal=journal,
        is_preprint=preprint, is_open_access=True, citations=0,
        topic="Test topic", abstract="An abstract about a thing that was measured.",
        authors=authors,
    )


def _author(name, oid=None, weizmann=True):
    return {
        "author": {"id": f"https://openalex.org/{oid}" if oid else "", "display_name": name},
        "institutions": [{"ror": "https://ror.org/0316ej306"}] if weizmann
        else [{"ror": "https://ror.org/01234abcd"}],
    }


def check(label: str, condition: bool, detail: str = "") -> bool:
    print(f"  {'PASS' if condition else 'FAIL'}  {label}{'  -> ' + detail if detail and not condition else ''}")
    return condition


def main() -> int:
    print("Checking config.yaml ...")
    config = Config.load()
    ok = check("config loads", True)
    ok &= check("ROR looks like an ID, not a URL", "/" not in config.institution_ror,
                config.institution_ror)
    ok &= check("at least one recipient", bool(config.recipients))

    print("\nChecking roster handling ...")
    tmp = ROOT / "out" / "_selftest_roster.csv"
    tmp.parent.mkdir(exist_ok=True)
    tmp.write_text(SAMPLE_ROSTER, encoding="utf-8")
    people = roster.load(tmp)
    ok &= check("inactive people are dropped", len(people) == 3, f"got {len(people)}")

    matcher = roster.Matcher(people, config.institution_ror, allow_name_fallback=True)

    by_id = _work("W1", "Matched by author ID", [_author("A. Lovelace", "A5000000001")])
    ok &= check("matches on OpenAlex author ID",
                [p.name for p in matcher.match(by_id)] == ["Ada Lovelace"])

    by_name = _work("W2", "Matched by name", [_author("Rosalind Franklin")])
    ok &= check("falls back to name when Weizmann-affiliated",
                [p.name for p in matcher.match(by_name)] == ["Rosalind Franklin"])

    elsewhere = _work("W3", "Same name, another institution",
                      [_author("Rosalind Franklin", weizmann=False)])
    ok &= check("ignores a same-name author at another institution",
                matcher.match(elsewhere) == [], str(matcher.match(elsewhere)))

    stranger = _work("W4", "Nobody we track", [_author("Unknown Person", "A5999999999")])
    ok &= check("ignores papers by people not on the roster", matcher.match(stranger) == [])

    reversed_name = _work("W5", "Comma-style name", [_author("Hodgkin, Dorothy", "A5000000003")])
    ok &= check("matches 'Surname, Given' spelling",
                [p.name for p in matcher.match(reversed_name)] == ["Dorothy Hodgkin"])

    print("\nChecking the email renders ...")
    items = [
        {"work": by_id, "people": matcher.match(by_id),
         "summary": "A paragraph describing what was found and why it matters.",
         "based_on": "abstract"},
        {"work": by_name, "people": matcher.match(by_name),
         "summary": "A second paragraph, this one without a real abstract behind it.",
         "based_on": "title_only"},
        {"work": _work("W6", "A preprint <with> & awkward characters",
                       [_author("A. Lovelace", "A5000000001")],
                       journal="bioRxiv", preprint=True),
         "people": [people[0]]},
    ]
    featured = [items[0]]

    html = render.html(items, featured, date.today())
    text = render.plain_text(items, featured, date.today())

    ok &= check("every paper appears in the HTML",
                all(i["work"].title.split("<")[0][:20] in html for i in items))
    ok &= check("HTML special characters are escaped", "&lt;with&gt; &amp;" in html)
    ok &= check("departments become section headings",
                "Computer Science and Applied Mathematics" in html)
    ok &= check("summaries reach the email", "why it matters" in html and "why it matters" in text)
    ok &= check("a title-only summary is flagged to the reader", "no abstract was available" in html)
    ok &= check("preprints are labelled", "preprint" in html.lower())
    ok &= check("plain-text version is not empty", len(text) > 200)

    print("\nChecking the sent-already record ...")
    state_file = ROOT / "out" / "_selftest_state.json"
    state_file.unlink(missing_ok=True)
    seen = SeenWorks(state_file)
    ok &= check("a fresh record is empty", by_id.id not in seen)
    seen.add(by_id.id)
    seen.save()
    ok &= check("reloads what it saved", by_id.id in SeenWorks(state_file))
    ok &= check("drops entries older than the retention window",
                _pruned_old(state_file) == 1)

    for leftover in (tmp, state_file):
        leftover.unlink(missing_ok=True)
    (ROOT / "out" / "_selftest_preview.html").write_text(html, encoding="utf-8")

    print(f"\n{'All checks passed.' if ok else 'SOME CHECKS FAILED - see above.'}")
    print("Sample email written to out/_selftest_preview.html - open it in a browser.")
    return 0 if ok else 1


def _pruned_old(path: Path) -> int:
    seen = SeenWorks(path)
    seen.seen["https://openalex.org/WOLD"] = "2020-01-01"
    return seen.prune()


if __name__ == "__main__":
    raise SystemExit(main())
