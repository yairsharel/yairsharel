"""Builds the clickable tracker page from the assigned queue.

The roster -- who is on each sender's list, in what order -- is baked into
the page, because it is reference data that only changes when the queue is
rebuilt. What each person DOES with the page (sent / already follows / not
found) is kept in the artifact's shared store instead, so it survives a
cleared browser, follows them between devices, and can be read back to
work out how deep the next list needs to run.
"""

import hashlib
import json
import re
from pathlib import Path

from .config import Config
from .load import Connection

TEMPLATE = Path(__file__).resolve().parent / "tracker_template.html"

SLUG = re.compile(r"linkedin\.com/in/([^/?#]+)", re.I)

# What the artifact store accepts as one path segment. A LinkedIn slug can
# contain characters outside this set -- an accent, a Hebrew name or an emoji
# arrives percent-encoded, and "%" is not legal here. Building a document
# reference from such a path throws synchronously, so the mark never saves and
# the next read erases it: the row looks simply unclickable.
LEGAL_SEGMENT = re.compile(r"^[A-Za-z0-9_\-.~:@+]{1,200}$")


def doc_id(slug: str) -> str:
    """A store-legal id for a slug, stable across rebuilds.

    A slug that is already legal is returned untouched, so ids stay the same
    and marks already recorded against them keep matching. Only the slugs that
    could never have been written get rewritten, with a hash of the original
    appended so two different slugs cannot collapse onto one id.
    """
    if LEGAL_SEGMENT.match(slug):
        return slug
    cleaned = re.sub(r"[^A-Za-z0-9_\-.~:@+]", "-", slug).strip("-") or "x"
    digest = hashlib.sha1(slug.encode("utf-8")).hexdigest()[:8]
    return f"{cleaned[:180]}-{digest}"


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
            key = doc_id(slug)
            if key in seen:           # two rows must never share a doc key
                key = f"{key}-{i}"
            seen.add(key)
            others = [a for a in person.reachable_by if a != admin_name]
            rows.append([
                key,
                person.name,
                person.position or "",
                person.company or "",
                person.score if person.score is not None else "",
                ", ".join(others),
                # The profile slug, only when the id had to be rewritten --
                # the link needs the real one, the store needs the legal one.
                slug if key != slug else "",
            ])

        bad = [r[0] for r in rows if not LEGAL_SEGMENT.match(r[0])]
        assert not bad, f"ids that the store would reject: {bad[:5]}"

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
