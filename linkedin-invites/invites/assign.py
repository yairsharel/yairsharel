"""Merges the exports, then decides which admin invites whom.

Each admin spends from their own credit pool and can only invite their own
1st-degree connections, so this is two decisions, not one:

  * Someone only one admin knows can only be invited by that admin.
  * Someone both admins know should be invited once, by whichever of them
    has the room -- inviting them twice wastes a credit and looks careless.
"""

from dataclasses import dataclass

from .config import Config
from .load import Connection


@dataclass
class MergeReport:
    total_rows: int
    unique_people: int
    shared: int

    @property
    def overlap_pct(self) -> float:
        return 100.0 * self.shared / self.unique_people if self.unique_people else 0.0


def merge(per_admin: dict[str, list[Connection]]) -> tuple[list[Connection], MergeReport]:
    merged: dict[str, Connection] = {}
    total_rows = 0

    for admin_name, connections in per_admin.items():
        for conn in connections:
            total_rows += 1
            existing = merged.get(conn.key)
            if existing is None:
                merged[conn.key] = conn
            elif admin_name not in existing.reachable_by:
                existing.reachable_by.append(admin_name)

    people = list(merged.values())
    report = MergeReport(
        total_rows=total_rows,
        unique_people=len(people),
        shared=sum(1 for p in people if len(p.reachable_by) > 1),
    )
    return people, report


def assign(people: list[Connection], cfg: Config) -> dict[str, list[Connection]]:
    """Hand each person to one admin, respecting credits and the target.

    Works down the list in score order, giving each person to whichever of
    the admins who can reach them has the most credits left. Highest scores
    get placed first, which is the property that matters; the headroom
    tiebreak then keeps one admin from being drained early while the other
    still holds credits their own connections cannot use.

    It is a greedy pass, not an optimal matching -- with two admins and a
    target well under the combined credits the difference is noise, but if
    you ever push the target close to the ceiling it could leave a few
    placeable people unplaced.
    """
    remaining = {a.name: a.credits for a in cfg.admins}
    assigned: dict[str, list[Connection]] = {a.name: [] for a in cfg.admins}
    placed = 0

    ranked = sorted(
        people,
        key=lambda p: (p.score if p.score is not None else -1, p.connected_date),
        reverse=True,
    )

    for person in ranked:
        if placed >= cfg.target:
            break
        if person.score is not None and person.score < cfg.min_score:
            continue

        candidates = [a for a in person.reachable_by if remaining.get(a, 0) > 0]
        if not candidates:
            continue

        chosen = max(candidates, key=lambda a: remaining[a])
        assigned[chosen].append(person)
        remaining[chosen] -= 1
        placed += 1

    return assigned
