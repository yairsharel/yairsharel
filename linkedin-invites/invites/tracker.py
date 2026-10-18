"""Builds the clickable tracker page from the assigned queue.

The roster -- who is on each sender's list, in what order -- is baked into
the page, because it is reference data that only changes when the queue is
rebuilt. What each person DOES with the page (sent / already follows / not
found) is kept in the artifact's shared store instead, so it survives a
cleared browser, follows them between devices, and can be read back to
work out how deep the next list needs to run.
"""

import json
import re
from pathlib import Path

from .config import Config
from .load import Connection

TEMPLATE = Path(__file__).resolve().parent / "tracker_template.html"

SLUG = re.compile(r"linkedin\.com/in/([^/?#]+)", re.I)


def _slug(conn: Connection, fallback: int) -> str:
    """A stable id per person, usable both as a doc key and a profile link."""
    match = SLUG.search(conn.url or "")
    if match:
        return match.group(1).lower()
    # No profile URL on the row. Keep it addressable, and accept that the
    # page cannot link to a profile it was never given.
    safe = re.sub(r"[^a-z0-9]+", "-", conn.name.lower()).strip("-")
    return f"x-{safe or 'unnamed'}-{fallback}"


def build(assigned: dict[str, list[Connection]], cfg: Config) -> str:
    by_name = {a.name: a for a in cfg.admins}
    lists = {}

    for admin_name, people in assigned.items():
        if not people:
            continue
        admin = by_name[admin_name]
        key = re.sub(r"[^a-z0-9]+", "-", admin_name.lower()).strip("-") or "sender"

        rows, seen = [], set()
        for i, person in enumerate(people):
            slug = _slug(person, i)
            if slug in seen:          # two rows must never share a doc key
                slug = f"{slug}-{i}"
            seen.add(slug)
            others = [a for a in person.reachable_by if a != admin_name]
            rows.append([
                slug,
                person.name,
                person.position or "",
                person.company or "",
                person.score if person.score is not None else "",
                ", ".join(others),
            ])

        lists[key] = {
            "name": admin_name,
            "credits": admin.credits,
            "rows": rows,
        }

    data = {"page": cfg.page_name, "lists": lists}
    html = TEMPLATE.read_text(encoding="utf-8")
    return html.replace("__DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def write(assigned: dict[str, list[Connection]], cfg: Config, path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(build(assigned, cfg), encoding="utf-8")
    return path
