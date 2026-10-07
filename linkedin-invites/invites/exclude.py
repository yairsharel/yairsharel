"""Removes people who already follow the page.

LinkedIn does not put the page's follower list in any export or API
response -- the Pages API returns follower *statistics* only. So the list
has to come from the page's own admin view, pasted in by hand.

The file is connections/already_following.txt, one person per line. Three
shapes all work, and they can be mixed:

    https://www.linkedin.com/in/ada-lovelace     a profile URL
    Ada Lovelace                                 a full name
    Ada Lovelace, PhD                            a name with a suffix

URLs are exact. Names are not: two people in a list of 8,869 can share
one, so a name match removes everyone who has it. That is the right trade
here -- failing to exclude a follower wastes a search, while wrongly
excluding someone only costs us a candidate from a list that has plenty.
"""

import re
import unicodedata
from pathlib import Path

from .load import Connection

# ", PhD", " M.D.", " (he/him)" and similar decorations people add.
SUFFIX = re.compile(
    r"\s*[,(–—|-]\s*(ph\.?d|m\.?d|m\.?sc|b\.?sc|msc|mba|prof|dr|"
    r"he/him|she/her|they/them)\b.*$",
    re.I,
)


def _norm_name(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").strip()
    value = SUFFIX.sub("", value)
    return re.sub(r"\s+", " ", value).casefold()


def _norm_url(value: str) -> str:
    u = (value or "").strip().lower()
    for prefix in ("https://", "http://", "www.", "linkedin.com"):
        if u.startswith(prefix):
            u = u[len(prefix):]
    return u.split("?")[0].rstrip("/")


def load_list(path: Path) -> tuple[set[str], set[str]]:
    """Returns (urls, names) to exclude. A missing file is not an error."""
    if not path.exists():
        return set(), set()

    urls, names = set(), set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "linkedin.com/in/" in line.lower():
            urls.add(_norm_url(line))
        else:
            names.add(_norm_name(line))
    return urls, names


def apply(
    people: list[Connection], path: Path
) -> tuple[list[Connection], dict[str, int]]:
    urls, names = load_list(path)
    if not urls and not names:
        return people, {"listed": 0, "removed": 0, "unmatched": 0}

    kept, matched_urls, matched_names = [], set(), set()
    for person in people:
        url_key = _norm_url(person.url)
        name_key = _norm_name(person.name)
        if url_key and url_key in urls:
            matched_urls.add(url_key)
        elif name_key and name_key in names:
            matched_names.add(name_key)
        else:
            kept.append(person)
            continue

    # Lines that matched nobody usually mean a typo or a different spelling,
    # so they are worth surfacing rather than silently ignoring.
    unmatched = (urls - matched_urls) | (names - matched_names)
    return kept, {
        "listed": len(urls) + len(names),
        "removed": len(people) - len(kept),
        "unmatched": len(unmatched),
        "unmatched_examples": sorted(unmatched)[:5],
    }
