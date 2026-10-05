"""Builds the invite queue. Run as: python -m invites.run"""

import argparse
from pathlib import Path

from . import assign as assign_mod
from . import config as config_mod
from . import load, queue, score

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    parser = argparse.ArgumentParser(description="Rank connections into an invite queue.")
    parser.add_argument(
        "--no-scoring",
        action="store_true",
        help="skip Claude and order by how recently you connected. Free, and "
        "enough to check the exports loaded and the assignment looks sane.",
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config.yaml")
    parser.add_argument("--out", type=Path, default=ROOT / "out" / "invite_queue.csv")
    args = parser.parse_args()

    cfg = config_mod.load(args.config)
    print(f"{cfg.page_name}: targeting {cfg.target} invites from "
          f"{cfg.total_credits} credits across {len(cfg.admins)} admins")

    per_admin = {}
    for admin in cfg.admins:
        connections = load.read_export(admin.export_path, admin.name)
        per_admin[admin.name] = connections
        print(f"  {admin.name}: {len(connections):,} connections, {admin.credits} credits")

    people, report = assign_mod.merge(per_admin)
    print(
        f"\n{report.total_rows:,} rows -> {report.unique_people:,} unique people "
        f"({report.shared:,} known to more than one admin, "
        f"{report.overlap_pct:.0f}% overlap)"
    )

    if args.no_scoring:
        print("\nskipping Claude (--no-scoring): ordering by connection date")
    else:
        print(f"\nscoring against the audience brief using {cfg.model}:")
        score.score_all(people, cfg)

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

    assigned = assign_mod.assign(people, cfg)
    written = queue.write(assigned, cfg, args.out)

    print(f"\nwrote {written:,} invites to {args.out}")
    for admin_name, group in assigned.items():
        if group:
            days = (len(group) - 1) // cfg.per_day + 1
            print(f"  {admin_name}: {len(group):,} invites over {days} days")
        else:
            print(f"  {admin_name}: nothing assigned")

    if written < cfg.target:
        print(
            f"\n{cfg.target - written} short of the target. That is a real "
            f"finding about the size of your reachable audience, not a bug."
        )


if __name__ == "__main__":
    main()
