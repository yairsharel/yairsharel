"""The list of ~350 PIs we track, and how a paper gets attributed to them."""

from __future__ import annotations

import csv
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

REQUIRED_COLUMNS = {"name", "openalex_author_id", "department", "active"}


@dataclass
class Person:
    name: str
    author_id: str
    department: str
    active: bool
    notes: str = ""
    name_keys: set[str] = field(default_factory=set)

    @property
    def has_id(self) -> bool:
        return bool(self.author_id)


def _strip_accents(text: str) -> str:
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def name_keys(full_name: str) -> set[str]:
    """Reduces a name to 'surname|first-initial' keys we can compare across sources.

    Handles "Yair Harel", "Harel, Yair", "Y. Harel", and accented spellings.
    Returns more than one key when the name has several parts and we cannot
    tell which is the surname (e.g. Spanish or compound names).
    """
    cleaned = _strip_accents(full_name).lower()
    cleaned = re.sub(r"[^a-z\s,'-]", " ", cleaned)

    if "," in cleaned:
        surname, _, rest = cleaned.partition(",")
        parts = [surname.strip()] + rest.split()
    else:
        parts = cleaned.split()

    parts = [p for p in parts if len(p) > 1 or p.isalpha()]
    if len(parts) < 2:
        return {parts[0].strip("-'")} if parts else set()

    if "," in cleaned:
        surname, given = parts[0], parts[1]
        return {f"{surname}|{given[0]}"}

    # No comma: assume last token is the surname, but also allow the first
    # token being the surname for "Harel Yair" style entries.
    first, last = parts[0], parts[-1]
    return {f"{last}|{first[0]}", f"{first}|{last[0]}"}


def normalise_author_id(value: str) -> str:
    """Accepts A5023888391 or the full https://openalex.org/A5023888391 URL."""
    value = (value or "").strip()
    if not value:
        return ""
    return "https://openalex.org/" + value.rstrip("/").rsplit("/", 1)[-1].upper()


def load(path: Path) -> list[Person]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - columns
        if missing:
            raise ValueError(
                f"roster.csv is missing these columns: {sorted(missing)}. "
                f"It has: {sorted(columns)}"
            )

        people: list[Person] = []
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            active = (row.get("active") or "yes").strip().lower() not in {"no", "false", "0"}
            people.append(
                Person(
                    name=name,
                    author_id=normalise_author_id(row.get("openalex_author_id", "")),
                    department=(row.get("department") or "Unassigned").strip() or "Unassigned",
                    active=active,
                    notes=(row.get("notes") or "").strip(),
                    name_keys=name_keys(name),
                )
            )

    active_people = [p for p in people if p.active]
    with_ids = sum(1 for p in active_people if p.has_id)
    log.info(
        "Roster: %d active people, %d with an OpenAlex author ID (%d matched by name only)",
        len(active_people), with_ids, len(active_people) - with_ids,
    )
    return active_people


class Matcher:
    """Decides which roster members, if any, are authors on a given work."""

    def __init__(self, people: list[Person], ror: str, allow_name_fallback: bool = True):
        self.ror = ror
        self.allow_name_fallback = allow_name_fallback
        self.by_id: dict[str, Person] = {p.author_id: p for p in people if p.has_id}

        # Only people without an ID need the name index - anyone with an ID is
        # matched exactly, and a name index entry could only add false hits.
        self.by_name: dict[str, list[Person]] = {}
        for person in people:
            if person.has_id:
                continue
            for key in person.name_keys:
                self.by_name.setdefault(key, []).append(person)

    def _is_weizmann(self, authorship: dict) -> bool:
        return any(
            (inst.get("ror") or "").rstrip("/").endswith(self.ror)
            for inst in authorship.get("institutions") or []
        )

    def match(self, work) -> list[Person]:
        found: dict[str, Person] = {}

        for authorship in work.authors:
            author = authorship.get("author") or {}
            author_id = (author.get("id") or "").strip()

            person = self.by_id.get(author_id)
            if person:
                found[person.name] = person
                continue

            if not self.allow_name_fallback or not self.by_name:
                continue
            # A name-only match is trusted only when OpenAlex also says this
            # author was at Weizmann on this paper. Surnames are not unique.
            if not self._is_weizmann(authorship):
                continue
            for key in name_keys(author.get("display_name") or ""):
                for candidate in self.by_name.get(key, []):
                    found[candidate.name] = candidate

        return list(found.values())
