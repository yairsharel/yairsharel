"""Reads LinkedIn's connections export.

The downloaded file is not quite a CSV. It opens with a few lines of notice
text and a blank line before the real header, which is why handing it
straight to csv.DictReader gets you nothing:

    Notes:
    "When exporting your connection data, you may notice that some of the
    email addresses are missing. ..."

    First Name,Last Name,URL,Email Address,Company,Position,Connected On

So we look for the header rather than assuming where it starts.
"""

import csv
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

HEADER_MARKER = "First Name"

# "05-???-26" -- a date whose month did not survive the export.
MASKED_MONTH = re.compile(r"^(\d{1,2})[-\s]+\?+[-\s]+(\d{2,4})$")


@dataclass
class Connection:
    first: str
    last: str
    url: str
    company: str
    position: str
    connected_on: str

    # Which admins have this person as a 1st-degree connection. Anyone with
    # more than one name here can be invited by any of them -- assign.py
    # picks which, since each admin spends from their own credit pool.
    reachable_by: list[str] = field(default_factory=list)

    score: int | None = None
    reason: str = ""

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}".strip()

    @property
    def connected_date(self) -> date:
        """`connected_on` as something sortable.

        LinkedIn writes this differently depending on the account's language,
        and one of the shapes is partly unreadable:

            04 Oct 2026     English account
            05-???-26       non-English account -- the month never rendered

        The second is not a parsing failure on our side; the month genuinely
        is not in the file. Day and year are, so those rows resolve to
        year precision (1 January of that year) rather than being thrown
        away. Ordering across years survives, ordering within a year does
        not, which is exactly as much as the file supports.

        Anything we cannot read at all sorts oldest, so an unexpected locale
        degrades to stable-but-arbitrary order instead of raising.
        """
        raw = (self.connected_on or "").strip()
        if not raw:
            return date.min

        for fmt in ("%d %b %Y", "%d %b %y", "%d-%b-%Y", "%d-%b-%y"):
            try:
                return datetime.strptime(raw, fmt).date()
            except ValueError:
                pass

        masked = MASKED_MONTH.match(raw)
        if masked:
            year = int(masked.group(2))
            if year < 100:
                year += 2000
            return date(year, 1, 1)

        return date.min

    @property
    def key(self) -> str:
        """What counts as the same person across two exports.

        The profile URL is the only identifier LinkedIn gives us that is
        actually stable. A handful of rows arrive without one, so those fall
        back to name plus employer -- good enough to catch the common case of
        two colleagues both knowing someone, and it will not merge two
        different people unless they share a name and an employer.
        """
        if self.url:
            u = self.url.strip().lower()
            for prefix in ("https://", "http://", "www.", "linkedin.com"):
                if u.startswith(prefix):
                    u = u[len(prefix):]
            return u.split("?")[0].rstrip("/")
        return f"{self.name.lower()}|{self.company.strip().lower()}"


def _header_offset(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if HEADER_MARKER in line:
            return i
    raise ValueError(
        f"no header row containing {HEADER_MARKER!r}. Is this really a LinkedIn "
        f"connections export? Settings & Privacy -> Data Privacy -> Get a copy "
        f"of your data -> Connections"
    )


def read_export(path: Path, admin_name: str) -> list[Connection]:
    if not path.exists():
        raise FileNotFoundError(
            f"{path} is missing. Drop the admin's connections CSV there under "
            f"the name given in config.yaml"
        )

    lines = path.read_text(encoding="utf-8-sig").splitlines()
    reader = csv.DictReader(lines[_header_offset(lines):])

    out = []
    for row in reader:
        row = {(k or "").strip(): (v or "").strip() for k, v in row.items()}
        first, last = row.get("First Name", ""), row.get("Last Name", "")
        if not (first or last):
            continue
        out.append(
            Connection(
                first=first,
                last=last,
                url=row.get("URL", ""),
                company=row.get("Company", ""),
                position=row.get("Position", ""),
                connected_on=row.get("Connected On", ""),
                reachable_by=[admin_name],
            )
        )
    return out
