"""Builds the invite queue. Run as: python -m invites.run"""

import argparse
from dataclasses import replace
from pathlib import Path

from . import assign as assign_mod
from . import config as config_mod
from . import exclude, load, queue, rules, score, worksheet

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank connections into an invite queue.")
    parser.add_argument(
        "--no-scoring",
        action="store_true",
        help="skip Claude and order by how recently you connected. Free, and "
        "enough to check the exports loaded and the assignment looks sane.",
    )
    parser.add_argument(
        "--rules",
        action="store_true",
        help="score with invites/rules.py instead of Claude. Free, instant and "
        "reproducible, but it only knows the titles it was taught.",
    )
    parser.add_argument(
        "--by-employer",
        action="store_true",
        help="order the worksheet by employer instead of by fit, so each "
        "heading maps to one filter in the invite panel. Writes an extra "
        "file; the fit-ordered one is still produced.",
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "invite_queue.csv")
    args = parser.parse_args()

    cfg = config_mod.load(args.config)
    print(f"{cfg.page_name}: targeting {cfg.target} invites from "
          f"{cfg.total_credits} credits across {len(cfg.admins)} admins")

    # Exports arrive one at a time, so a missing one is a normal state to be
    # in rather than an error. It is called out loudly instead, because a
    # queue built from one admin's list is a different thing from the queue
    # you asked for.
    per_admin = {}
    missing = []
    for admin in cfg.admins:
        if not admin.export_path.exists():
            missing.append(admin)
            print(f"  {admin.name}: export not found at connections/{admin.export}")
            continue
        connections = load.read_export(admin.export_path, admin.name)
        per_admin[admin.name] = connections
        print(f"  {admin.name}: {len(connections):,} connections, {admin.credits} credits")

    if not per_admin:
        raise SystemExit("\nno exports found in connections/ -- nothing to rank")

    people, report = assign_mod.merge(per_admin)
    print(
        f"\n{report.total_rows:,} rows -> {report.unique_people:,} unique people "
        f"({report.shared:,} known to more than one admin, "
        f"{report.overlap_pct:.0f}% overlap)"
    )

    people, excl = exclude.apply(people, cfg.exclude_path)
    if excl["listed"]:
        print(
            f"\nexcluded {excl['removed']:,} people already following the page "
            f"({excl['listed']:,} listed in connections/{cfg.exclude_file})"
        )
        if excl["unmatched"]:
            print(
                f"  {excl['unmatched']} listed names matched nobody -- check the "
                f"spelling, e.g. {', '.join(excl['unmatched_examples'][:3])}"
            )
        print(f"  {len(people):,} candidates remain")
    else:
        where = (
            f"connections/{cfg.exclude_file} lists nobody yet"
            if cfg.exclude_path.exists()
            else f"no connections/{cfg.exclude_file}"
        )
        buffers = ", ".join(
            f"{a.name} {a.rows(cfg.overshoot) - a.credits:+d}" for a in cfg.admins
        )
        print(
            f"\n{where}, so people who already follow the page are still in the "
            f"list and will have to be skipped as you hit them. Rows above each "
            f"credit balance, to absorb that: {buffers}."
        )

    if args.no_scoring:
        print("\nskipping scoring (--no-scoring): ordering by connection date")
    elif args.rules:
        print("\nscoring by rule (--rules), not by model:")
        rules.score_all(people)
    else:
        print(f"\nscoring against the audience brief using {cfg.model}:")
        score.score_all(people, cfg)

    if not args.no_scoring:
        scored = [p for p in people if p.score is not None]
        if scored:
            above = sum(1 for p in scored if p.score >= cfg.min_score)
            print(
                f"  {above:,} of {len(scored):,} scored at or above "
                f"min_score {cfg.min_score}"
            )
            if above < cfg.target:
                print(
                    f"  note: that is fewer than the target of {cfg.target}. The "
                    f"queue will be short -- widen the brief, add an admin, or "
                    f"lower min_score, but do not lower it just to fill the sheet."
                )

    # Only the admins we actually have a list for can be assigned anything.
    present = [a for a in cfg.admins if a.name in per_admin]
    cfg_present = replace(cfg, admins=present)

    assigned = assign_mod.assign(people, cfg_present)
    written = queue.write(assigned, cfg_present, args.out)
    per_admin_files = queue.write_per_admin(assigned, cfg_present, args.out.parent)
    sheets = worksheet.write(assigned, cfg_present, args.out.parent)
    if args.by_employer:
        sheets.update(
            worksheet.write(assigned, cfg_present, args.out.parent, by_employer=True)
        )

    print(f"\nwrote {written:,} invites to {args.out}")
    for admin_name, group in assigned.items():
        if group:
            days = (len(group) - 1) // cfg.per_day + 1
            where = per_admin_files.get(admin_name)
            print(f"  {admin_name}: {len(group):,} invites in {days} batches"
                  + (f" -> {where.name}" if where else "")
                  + (f", {sheets[admin_name].name}" if admin_name in sheets else ""))
        else:
            print(f"  {admin_name}: nothing assigned")

    if missing:
        names = ", ".join(a.name for a in missing)
        held = sum(a.credits for a in missing)
        print(
            f"\nThis queue is partial: no export for {names}, so {held} credits "
            f"are not represented. Re-run once the export lands -- the ranking "
            f"will shift, because people you both know get assigned once."
        )
    elif written < cfg.target:
        print(
            f"\n{cfg.target - written} short of the target. That is a real "
            f"finding about the size of your reachable audience, not a bug."
        )


if __name__ == "__main__":
    main()
