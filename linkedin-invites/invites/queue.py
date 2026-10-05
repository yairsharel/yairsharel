"""Writes out/invite_queue.csv -- the sheet the admins actually work from."""

import csv
from pathlib import Path

from .config import Config
from .load import Connection

COLUMNS = [
    "day",
    "admin",
    "rank",
    "name",
    "profile_url",
    "company",
    "position",
    "score",
    "reason",
    "also_reachable_by",
    "status",
]


def write(assigned: dict[str, list[Connection]], cfg: Config, path: Path) -> int:
    rows = []

    for admin_name, people in assigned.items():
        for i, person in enumerate(people):
            others = [a for a in person.reachable_by if a != admin_name]
            rows.append(
                {
                    "day": i // cfg.per_day + 1,
                    "admin": admin_name,
                    "rank": i + 1,
                    "name": person.name,
                    "profile_url": person.url,
                    "company": person.company,
                    "position": person.position,
                    "score": person.score if person.score is not None else "",
                    "reason": person.reason,
                    "also_reachable_by": ", ".join(others),
                    "status": "",
                }
            )

    rows.sort(key=lambda r: (r["day"], r["admin"], r["rank"]))

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
