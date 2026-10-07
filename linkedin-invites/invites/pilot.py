"""A short probe to run before committing anyone to an hour of clicking.

Three things about the manual route are unknown until someone tries it:
how long one invite takes, what share of the list already follows the
page, and whether the invite panel can filter by company or only search
by name. All three are cheap to measure and expensive to guess at, so each
sender gets a 25-name sheet with somewhere to write the answers down.
"""

from pathlib import Path

from .config import Admin, Config
from .load import Connection

SIZE = 25


def _header(admin: Admin, cfg: Config, rows: int, n: int) -> list[str]:
    edge = 1 - admin.credits / rows if rows else 0.0
    edge_count = round(edge * n)
    per_credit = admin.credits / n if n else 0

    return [
        f"PILOT -- {admin.name}. {n} invites, to find out whether the manual",
        "route works before anyone commits an afternoon to it.\n",
        "Send only these. Record what happens. The answers decide whether to",
        "work the full list, deepen it, or price ads instead.\n",
        "=" * 68,
        "A. THREE QUESTIONS ABOUT THE PANEL  (answer while you are in it)",
        "=" * 68,
        "",
        "  1. Can you FILTER the invitable list by company or school, or is",
        "     name search the only way to find someone?",
        "       filter available?   YES / NO    ..............................",
        "",
        "  2. Can you tick SEVERAL people and send one batch, or is it one",
        "     invite per action?",
        "       multi-select?       YES / NO    ..............................",
        "",
        "  3. Roughly how many connections does the panel show before you",
        "     have to scroll or page?",
        "       roughly             ............",
        "",
        "=" * 68,
        "B. TIME IT",
        "=" * 68,
        "",
        "  start  ..........      end  ..........",
        "",
        f"  Multiply whatever these {n} take by {per_credit:.0f} for your "
        f"{admin.credits} credits.",
        "  Under 8 minutes here is under an hour in total, which is fine.",
        "  Over 20 minutes is over two hours, and ads are worth pricing.",
        "",
        "=" * 68,
        f"C. THE {n}",
        "=" * 68,
        "",
        "  Mark each:   S = sent    F = already following    X = not found",
        "",
    ]


def _footer(admin: Admin, rows: int, n: int) -> list[str]:
    edge = 1 - admin.credits / rows if rows else 0.0
    e = round(edge * n)
    return [
        "=" * 68,
        "D. WHAT THE NUMBERS MEAN",
        "=" * 68,
        "",
        f"  Count the F marks out of {n}.",
        "",
        f"  The full list is {rows} rows for {admin.credits} credits, so it",
        f"  survives an already-following rate up to {edge * 100:.0f}%.",
        "",
        f"    0-{max(e - 3, 0)} already following    fine, work straight through",
        f"    {max(e - 2, 1)}-{e + 2} already following    borderline -- ask for a deeper list",
        f"    {e + 3}+ already following     {rows} rows will not reach {admin.credits} sends",
        "",
        "  Note anything the ranking got wrong too -- someone near the top you",
        "  would not have picked. The first rows are where a bad brief shows.",
        "",
    ]


def write(
    assigned: dict[str, list[Connection]],
    cfg: Config,
    directory: Path,
    size: int = SIZE,
) -> dict[str, Path]:
    out = {}
    by_name = {a.name: a for a in cfg.admins}

    for admin_name, people in assigned.items():
        if not people:
            continue
        admin = by_name[admin_name]
        sample = people[:size]

        lines = _header(admin, cfg, len(people), len(sample))
        for i, person in enumerate(sample, 1):
            lines.append(f"  [ ] {i:2}. {person.name}")
            if person.position:
                lines.append(f"          {person.position[:62]}")
            if person.company:
                lines.append(f"          {person.company[:62]}")
            lines.append("")
        lines += _footer(admin, len(people), len(sample))

        path = directory / f"pilot_{admin_name.lower().replace(' ', '-')}.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        out[admin_name] = path
    return out
