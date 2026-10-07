"""Emits a plain-text worksheet to click from.

The CSV is the record; this is the thing you keep open while working the
Invite connections panel. Sending is a loop of: paste a name into the
panel's search box, tick the checkbox, move on. So the worksheet puts the
name first and alone on its line, with the title underneath as a check
that you ticked the right person -- two people called Yael Cohen is not a
hypothetical in a list this size.
"""

from pathlib import Path

from .config import Config
from .load import Connection

HEADER = """\
{admin} -- {credits} credits to spend, {total} names to work through

  LinkedIn page -> Admin tools -> Invite connections. Paste each name into
  that panel's search box, tick the box, send.

  WHERE TO STOP
  Stop when you have SENT {credits} invites -- not when you reach the end of
  this list. The list is longer than your budget on purpose: people who
  already follow the page cannot be invited, and LinkedIn will not tell us
  in advance who they are. Skipping one of those costs you a search, not a
  credit. {total} names should be enough to get {credits} invites out.

  If you run out of names before spending {credits} credits, say so -- it
  means the already-following rate is higher than the {overshoot:g}x this
  list was built for, and the list needs to run deeper.

  MARK WHAT HAPPENS
  In the CSV, put "sent" or "already following" against each row. The
  second one is the number worth having: it tells us how much deeper the
  next list needs to run, and it is not recoverable afterwards.

  BATCH 1 FIRST
  Send batch 1, then wait about 48 hours and check the acceptance rate
  before the rest. An accepted invite refunds its credit; a declined or
  ignored one does not, so a wrong audience brief burns credits
  permanently. Under about 20% acceptance, stop and revise the brief.

  SHARED NAMES
  A name marked [also {others}] can be invited by either of you. It is
  assigned here, so only you should send it. A duplicate spends two
  credits to reach one person.

"""


GROUPED_NOTE = """\
  HOW THIS LIST IS ORDERED
  By employer, largest group first -- not by fit. If the invite panel lets
  you filter by company, each heading below is one filter: set it, tick the
  people listed, move to the next heading. That turns a few hundred name
  searches into a few dozen actions.

  The trade: you are no longer working in strict fit order, so the people
  you invite first are not quite the best-ranked ones. Each name still
  carries its fit score, and nobody below min_score is here at all. For a
  list dominated by one employer the difference is negligible; for a long
  tail of one-person employers it is real but small, because the employer
  is most of what drives the score anyway.

  Fit order is in the CSV, and worksheet order can be switched back by
  re-running without --by-employer.

"""


def _shared(person: Connection, admin_name: str) -> str:
    others = [a for a in person.reachable_by if a != admin_name]
    return f"   [also reachable by {', '.join(others)}]" if others else ""


def _grouped(people: list[Connection]) -> list[tuple[str, list[Connection]]]:
    """Employer groups, biggest first, rank order preserved inside each."""
    groups: dict[str, list[Connection]] = {}
    for person in people:
        groups.setdefault(person.company or "(no employer given)", []).append(person)
    return sorted(groups.items(), key=lambda kv: (-len(kv[1]), kv[0]))


def write(
    assigned: dict[str, list[Connection]],
    cfg: Config,
    directory: Path,
    by_employer: bool = False,
) -> dict[str, Path]:
    out = {}
    for admin_name, people in assigned.items():
        if not people:
            continue

        others = ", ".join(a.name for a in cfg.admins if a.name != admin_name)
        credits = next(
            (a.credits for a in cfg.admins if a.name == admin_name), len(people)
        )
        batches = (len(people) - 1) // cfg.per_day + 1
        lines = [
            HEADER.format(
                admin=admin_name,
                credits=credits,
                total=len(people),
                batches=batches,
                per_batch=cfg.per_day,
                overshoot=cfg.overshoot,
                others=others or "the other admin",
            )
        ]

        if by_employer:
            lines.append(GROUPED_NOTE)
            for employer, members in _grouped(people):
                lines.append(f"\n{'-' * 68}\n{employer}   ({len(members)})\n{'-' * 68}")
                for person in members:
                    lines.append(f"  [ ] {person.name}{_shared(person, admin_name)}")
                    lines.append(f"        {(person.position or '')[:80]}   (fit {person.score})")
        else:
            for i, person in enumerate(people):
                if i % cfg.per_day == 0:
                    lines.append(
                        f"\n{'=' * 68}\nBATCH {i // cfg.per_day + 1} of {batches}"
                        f"   (invites {i + 1}-{min(i + cfg.per_day, len(people))}"
                        f" of {len(people)})\n{'=' * 68}\n"
                    )
                lines.append(f"  [ ] {person.name}{_shared(person, admin_name)}")
                detail = " / ".join(x for x in (person.position, person.company) if x)
                lines.append(f"        {detail[:88]}   (fit {person.score})")

        suffix = "_by_employer" if by_employer else ""
        path = (
            directory
            / f"worksheet_{admin_name.lower().replace(' ', '-')}{suffix}.txt"
        )
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out[admin_name] = path
    return out
