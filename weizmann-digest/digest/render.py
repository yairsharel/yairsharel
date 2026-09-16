"""Turns the week's matched papers into the HTML and plain-text email bodies.

Email clients are not browsers. Outlook in particular ignores most modern CSS,
so this uses tables, inline styles and web-safe fonts on purpose.
"""

from __future__ import annotations

import textwrap
from collections import defaultdict
from datetime import date
from html import escape

INK = "#1a1a1a"
MUTED = "#5f6b7a"
RULE = "#e2e6ea"
ACCENT = "#0b5d8f"
FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"


def _authors(work, people) -> str:
    """Names of our own PIs on the paper, with a hint at the wider author list."""
    ours = ", ".join(p.name for p in people)
    total = len(work.authors)
    if total > len(people):
        others = total - len(people)
        ours += f" <span style='color:{MUTED}'>+{others} other author{'s' if others > 1 else ''}</span>"
    return ours


def _tag(text: str, colour: str) -> str:
    return (
        f"<span style=\"display:inline-block;font-size:11px;font-weight:600;"
        f"letter-spacing:.03em;text-transform:uppercase;color:{colour};"
        f"border:1px solid {colour};border-radius:3px;padding:1px 5px;"
        f"margin-right:6px;\">{escape(text)}</span>"
    )


def _tags(work) -> str:
    out = ""
    if work.is_preprint:
        out += _tag("preprint", "#a15c00")
    if work.is_open_access:
        out += _tag("open access", "#1d7a4c")
    return out


def _paper_row(item: dict, featured: bool = False) -> str:
    work, people = item["work"], item["people"]
    title = escape(work.title)
    journal = escape(work.journal)

    body = (
        f"<div style=\"font-size:15px;line-height:1.45;font-weight:600;margin:0 0 4px;\">"
        f"<a href=\"{escape(work.url)}\" style=\"color:{ACCENT};text-decoration:none;\">{title}</a>"
        f"</div>"
        f"<div style=\"font-size:13px;line-height:1.5;color:{MUTED};margin:0 0 3px;\">"
        f"{_authors(work, people)}</div>"
        f"<div style=\"font-size:13px;line-height:1.5;color:{MUTED};\">"
        f"{_tags(work)}<em>{journal}</em>"
        f"{' &middot; ' + escape(work.published) if work.published else ''}</div>"
    )

    if item.get("summary"):
        caveat = (
            f"<span style=\"color:{MUTED};\"> (no abstract was available - "
            f"written from the title and venue)</span>"
            if item.get("based_on") == "title_only"
            else ""
        )
        size = 15 if featured else 14
        body += (
            f"<div style=\"font-size:{size}px;line-height:1.6;color:{INK};margin:9px 0 0;\">"
            f"{escape(item['summary'])}{caveat}</div>"
        )

    return (
        f"<tr><td style=\"padding:12px 0;border-bottom:1px solid {RULE};\">{body}</td></tr>"
    )


def _section(title: str, rows: str, subtitle: str = "") -> str:
    sub = (
        f"<div style=\"font-size:13px;color:{MUTED};margin:2px 0 0;\">{escape(subtitle)}</div>"
        if subtitle
        else ""
    )
    return (
        f"<tr><td style=\"padding:26px 0 2px;\">"
        f"<div style=\"font-size:12px;font-weight:700;letter-spacing:.08em;"
        f"text-transform:uppercase;color:{INK};\">{escape(title)}</div>{sub}</td></tr>"
        f"{rows}"
    )


def html(items: list[dict], featured: list[dict], issue_date: date) -> str:
    featured_ids = {f["work"].id for f in featured}

    parts: list[str] = []

    if featured:
        rows = "".join(_paper_row(item, featured=True) for item in featured)
        parts.append(_section("Worth a look", rows, "Selected from this week's papers"))

    by_department: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        if item["work"].id in featured_ids:
            continue
        for person in item["people"] or []:
            by_department[person.department].append(item)
        if not item["people"]:
            by_department["Unmatched Weizmann authors"].append(item)

    for department in sorted(by_department, key=lambda d: (d.startswith("Unmatched"), d.lower())):
        papers = by_department[department]
        # The same paper can sit under two departments when it is a
        # collaboration; that is intentional, each group sees its own work.
        unique = {p["work"].id: p for p in papers}.values()
        rows = "".join(
            _paper_row(item)
            for item in sorted(unique, key=lambda i: i["work"].published, reverse=True)
        )
        parts.append(_section(department, rows, f"{len(unique)} paper{'s' if len(unique) != 1 else ''}"))

    count = len(items)
    header = (
        f"<tr><td style=\"padding:0 0 4px;\">"
        f"<div style=\"font-size:21px;font-weight:700;color:{INK};\">Weizmann publications</div>"
        f"<div style=\"font-size:13px;color:{MUTED};margin-top:3px;\">"
        f"Week of {issue_date.strftime('%-d %B %Y')} &middot; "
        f"{count} new paper{'s' if count != 1 else ''}</div>"
        f"</td></tr>"
    )

    footer = (
        f"<tr><td style=\"padding:26px 0 0;border-top:1px solid {RULE};font-size:12px;"
        f"line-height:1.6;color:{MUTED};\">"
        f"Assembled automatically from OpenAlex, which indexes Crossref, PubMed, arXiv, "
        f"bioRxiv and other sources. Featured summaries are written by Claude and are not "
        f"checked by a person before sending &mdash; read the paper before quoting it. "
        f"A missing group or a wrong name usually means a roster entry needs fixing."
        f"</td></tr>"
    )

    return (
        f"<div style=\"background:#f6f7f9;padding:24px 12px;\">"
        f"<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" "
        f"width=\"100%\" style=\"max-width:660px;margin:0 auto;background:#ffffff;"
        f"border:1px solid {RULE};border-radius:6px;\">"
        f"<tr><td style=\"padding:28px 30px 30px;font-family:{FONT};color:{INK};\">"
        f"<table role=\"presentation\" cellpadding=\"0\" cellspacing=\"0\" border=\"0\" width=\"100%\">"
        f"{header}{''.join(parts)}{footer}"
        f"</table></td></tr></table></div>"
    )


def _text_entry(item: dict) -> list[str]:
    work = item["work"]
    lines = [
        f"* {work.title}",
        f"  {', '.join(p.name for p in item['people']) or 'unmatched'} - {work.journal}",
    ]
    if item.get("summary"):
        lines += ["  " + line for line in textwrap.wrap(item["summary"], 76)]
    lines += [f"  {work.url}", ""]
    return lines


def plain_text(items: list[dict], featured: list[dict], issue_date: date) -> str:
    lines = [
        "WEIZMANN PUBLICATIONS",
        f"Week of {issue_date.strftime('%-d %B %Y')} - {len(items)} new papers",
        "",
    ]

    if featured:
        lines += ["WORTH A LOOK", ""]
        for item in featured:
            work = item["work"]
            lines += _text_entry(item)

    featured_ids = {f["work"].id for f in featured}
    by_department: dict[str, list[dict]] = defaultdict(list)
    for item in items:
        if item["work"].id in featured_ids:
            continue
        for person in item["people"] or []:
            by_department[person.department].append(item)
        if not item["people"]:
            by_department["Unmatched Weizmann authors"].append(item)

    for department in sorted(by_department, key=lambda d: (d.startswith("Unmatched"), d.lower())):
        lines += [department.upper(), ""]
        for item in {p["work"].id: p for p in by_department[department]}.values():
            lines += _text_entry(item)

    return "\n".join(lines)
