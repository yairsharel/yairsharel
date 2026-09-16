"""Builds and sends the weekly digest.

    python -m digest.run --dry-run    # write out/preview.html, send nothing
    python -m digest.run              # the real thing
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

from . import mailer, openalex, render, roster, summarize
from .config import ROOT, Config, smtp_settings
from .state import SeenWorks

log = logging.getLogger("digest")


def build(config: Config, since: date, seen, summarize_papers: bool = True) -> tuple[list, list]:
    people = roster.load(ROOT / "roster.csv")
    if not people:
        raise SystemExit("roster.csv has no active people in it - nothing to report on.")

    matcher = roster.Matcher(people, config.institution_ror, config.allow_name_fallback)

    items: list[dict] = []
    skipped = {"already_sent": 0, "old": 0, "wrong_type": 0, "preprint": 0, "no_match": 0}
    this_year = date.today().year

    for work in openalex.fetch_recent(config.institution_ror, config.contact_email, since):
        if work.id in seen:
            skipped["already_sent"] += 1
            continue
        if work.work_type in config.exclude_types:
            skipped["wrong_type"] += 1
            continue
        if work.is_preprint and not config.include_preprints:
            skipped["preprint"] += 1
            continue
        if (
            config.max_publication_age_years
            and work.year
            and work.year < this_year - config.max_publication_age_years
        ):
            skipped["old"] += 1
            continue

        matched = matcher.match(work)
        if not matched:
            # A Weizmann paper by someone not on our roster - students,
            # visitors, groups we do not track. Not an error, just not ours.
            skipped["no_match"] += 1
            continue

        items.append({"work": work, "people": matched})

    log.info("Kept %d papers. Skipped: %s", len(items), skipped)

    if not items:
        return [], []

    if summarize_papers:
        summarize.summarize_all(items, concurrency=config.summary_concurrency,
                                limit=config.max_summaries)
        featured = summarize.choose_featured(items, config.highlight_count)
    else:
        log.info("Summaries disabled for this run")
        featured = []

    return items, featured


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and send the Weizmann publications digest")
    parser.add_argument("--dry-run", action="store_true",
                        help="Write out/preview.html and send nothing. State is not updated.")
    parser.add_argument("--since", type=date.fromisoformat, metavar="YYYY-MM-DD",
                        help="Override the start of the window (default: config lookback_days ago)")
    parser.add_argument("--no-summaries", action="store_true",
                        help="Skip Claude entirely - a fast, free structure check")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(name)s: %(message)s",
        stream=sys.stdout,
    )

    config = Config.load()
    since = args.since or openalex.default_since(config.lookback_days)
    today = date.today()
    log.info("Looking for papers OpenAlex indexed since %s", since)

    # Fail before spending anything on Claude if the credentials are missing.
    smtp = None if args.dry_run else smtp_settings()

    seen = SeenWorks(ROOT / "state" / "seen_works.json")

    items, featured = build(config, since, seen, summarize_papers=not args.no_summaries)

    if not items:
        log.info("No new papers this week - not sending an empty email.")
        return 0

    html_body = render.html(items, featured, today)
    text_body = render.plain_text(items, featured, today)
    subject = f"{config.subject_prefix} - {today:%-d %B %Y} ({len(items)} new)"

    out = ROOT / "out"
    out.mkdir(exist_ok=True)
    (out / "preview.html").write_text(html_body, encoding="utf-8")
    (out / "preview.txt").write_text(text_body, encoding="utf-8")
    (out / "papers.json").write_text(
        json.dumps(
            [
                {
                    "id": i["work"].short_id,
                    "title": i["work"].title,
                    "url": i["work"].url,
                    "journal": i["work"].journal,
                    "published": i["work"].published,
                    "preprint": i["work"].is_preprint,
                    "people": [p.name for p in i["people"]],
                    "departments": sorted({p.department for p in i["people"]}),
                    "summary": i.get("summary"),
                    "based_on": i.get("based_on"),
                    "featured": any(f["work"].id == i["work"].id for f in featured),
                    "why_featured": i.get("why_featured"),
                }
                for i in items
            ],
            indent=2, ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    log.info("Wrote out/preview.html, out/preview.txt and out/papers.json")

    if args.dry_run:
        log.info("Dry run - nothing sent, state not updated.")
        return 0

    mailer.send(subject, html_body, text_body, config.recipients, smtp)

    for item in items:
        seen.add(item["work"].id, today)
    seen.save()
    log.info("Recorded %d papers as sent.", len(items))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
