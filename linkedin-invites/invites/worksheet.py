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
{admin} -- {total} invites to send, in {batches} batches of {per_batch}

  LinkedIn page -> Admin tools -> Invite connections. Paste each name into
  that panel's search box, tick the box, and send the batch.

  Send BATCH 1 first, then wait about 48 hours and check the acceptance
  rate before sending the rest. An accepted invite refunds its credit; a
  declined or ignored one does not. If batch 1 comes back under 20%, stop
  and revise page.audience in config.yaml -- the remaining credits are
  worth more than the time saved by pressing on.

  Shared: a name marked [also {others}] can be invited by either of you.
  Only one of you should. These are assigned here.

"""


def write(
    assigned: dict[str, list[Connection]], cfg: Config, directory: Path
) -> dict[str, Path]:
    out = {}
    for admin_name, people in assigned.items():
        if not people:
            continue

        others = ", ".join(a.name for a in cfg.admins if a.name != admin_name)
        batches = (len(people) - 1) // cfg.per_day + 1
        lines = [
            HEADER.format(
                admin=admin_name,
                total=len(people),
                batches=batches,
                per_batch=cfg.per_day,
                others=others or "the other admin",
            )
        ]

        for i, person in enumerate(people):
            if i % cfg.per_day == 0:
                done = i
                lines.append(
                    f"\n{'=' * 68}\nBATCH {i // cfg.per_day + 1} of {batches}"
                    f"   (invites {i + 1}-{min(i + cfg.per_day, len(people))}"
                    f" of {len(people)})\n{'=' * 68}\n"
                )
            shared = (
                f"   [also reachable by {', '.join(a for a in person.reachable_by if a != admin_name)}]"
                if len(person.reachable_by) > 1
                else ""
            )
            lines.append(f"  [ ] {person.name}{shared}")
            detail = " / ".join(x for x in (person.position, person.company) if x)
            lines.append(f"        {detail[:88]}   (fit {person.score})")

        path = directory / f"worksheet_{admin_name.lower().replace(' ', '-')}.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out[admin_name] = path
    return out
