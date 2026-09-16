"""One-time helper: find each PI's OpenAlex author ID from their name.

    python -m digest.resolve_roster

Reads roster.csv, looks up every row that has no ID yet, and writes
roster_resolved.csv with the best candidate, a confidence column and the
alternatives. Review that file, fix what is wrong, then rename it over
roster.csv. It never overwrites roster.csv itself.

Why bother: a name match can confuse two people with the same surname and
initial. An author ID cannot. Ten minutes of review here removes a whole class
of embarrassing mistakes from every future issue.
"""

from __future__ import annotations

import csv
import logging
import sys
import time

import requests

from .config import ROOT, Config
from .roster import Person, load, name_keys

log = logging.getLogger("resolve")

AUTHORS_API = "https://api.openalex.org/authors"


def candidates(session: requests.Session, person: Person, ror: str, email: str) -> list[dict]:
    """OpenAlex authors affiliated with Weizmann whose name looks like this person's."""
    params = {
        "filter": f"affiliations.institution.ror:{ror}",
        "search": person.name,
        "per-page": "10",
        "mailto": email,
    }
    try:
        response = session.get(AUTHORS_API, params=params, timeout=60)
        response.raise_for_status()
    except requests.RequestException as exc:
        log.warning("Lookup failed for %s: %s", person.name, exc)
        return []
    return response.json().get("results", [])


def score(person: Person, candidate: dict) -> str:
    """How much we trust this match. `high` is safe to accept without reading."""
    their_keys = name_keys(candidate.get("display_name") or "")
    if not (person.name_keys & their_keys):
        return "low"
    alternates = {
        key
        for alt in candidate.get("display_name_alternatives") or []
        for key in name_keys(alt)
    }
    works = candidate.get("works_count") or 0
    if person.name.lower() == (candidate.get("display_name") or "").lower() and works > 5:
        return "high"
    if person.name_keys & (their_keys | alternates) and works > 5:
        return "medium"
    return "low"


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)-7s %(message)s", stream=sys.stdout)
    config = Config.load()
    people = load(ROOT / "roster.csv")
    session = requests.Session()

    rows, counts = [], {"already": 0, "high": 0, "medium": 0, "low": 0, "none": 0}

    for n, person in enumerate(people, 1):
        if person.has_id:
            counts["already"] += 1
            rows.append(
                {
                    "name": person.name,
                    "openalex_author_id": person.author_id,
                    "department": person.department,
                    "active": "yes",
                    "notes": person.notes,
                    "confidence": "already set",
                    "matched_name": "",
                    "works_count": "",
                    "alternatives": "",
                }
            )
            continue

        found = candidates(session, person, config.institution_ror, config.contact_email)
        ranked = sorted(
            ((score(person, c), c) for c in found),
            key=lambda pair: ({"high": 0, "medium": 1, "low": 2}[pair[0]], -(pair[1].get("works_count") or 0)),
        )

        if not ranked or ranked[0][0] == "low":
            counts["none" if not ranked else "low"] += 1
            best_conf, best = ("no match" if not ranked else "low"), (ranked[0][1] if ranked else {})
        else:
            best_conf, best = ranked[0]
            counts[best_conf] += 1

        rows.append(
            {
                "name": person.name,
                "openalex_author_id": best.get("id", "") if best_conf != "no match" else "",
                "department": person.department,
                "active": "yes",
                "notes": person.notes,
                "confidence": best_conf,
                "matched_name": best.get("display_name", ""),
                "works_count": best.get("works_count", ""),
                "alternatives": " | ".join(
                    f"{c.get('display_name')} ({c.get('id','').rsplit('/',1)[-1]}, "
                    f"{c.get('works_count')} works)"
                    for _, c in ranked[1:4]
                ),
            }
        )

        if n % 25 == 0:
            log.info("%d/%d looked up", n, len(people))
        time.sleep(0.12)  # stay well inside OpenAlex's 10 requests/second

    out = ROOT / "roster_resolved.csv"
    with out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    log.info("Wrote %s", out)
    log.info("Results: %s", counts)
    log.info(
        "Now open it in Excel, sort by the `confidence` column, and check every "
        "row that is not `high`. Then rename it over roster.csv."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
