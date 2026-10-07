"""Offline check on invented data. No network, no API key, no cost.

Run as: python -m invites.selftest

Covers the parts that can quietly do the wrong thing -- LinkedIn's preamble,
deduplicating two admins' overlapping connections, and keeping the
assignment inside each admin's credit pool.
"""

import csv
import tempfile
from datetime import date
from pathlib import Path

from .assign import assign, merge
from .config import Admin, Config
from .load import read_export
from .queue import write

# What the download actually looks like: notice text, a blank line, then
# the header. Anything that assumes row 1 is the header reads nothing.
EXPORT_TEMPLATE = """\
Notes:
"When exporting your connection data, you may notice that some of the email \
addresses are missing. This is because of the privacy settings members have \
chosen for their accounts."

First Name,Last Name,URL,Email Address,Company,Position,Connected On
{rows}
"""

ALICE_ROWS = [
    ("Ada", "Lovelace", "https://www.linkedin.com/in/ada/", "", "Cambridge", "Professor", "01 Jan 2024"),
    ("Grace", "Hopper", "https://www.linkedin.com/in/grace/", "", "Yale", "Research Scientist", "02 Jan 2024"),
    ("Alan", "Turing", "https://www.linkedin.com/in/alan/", "", "NPL", "Group Leader", "03 Jan 2024"),
    ("Rosalind", "Franklin", "https://www.linkedin.com/in/rosalind/", "", "King's", "Postdoc", "04 Jan 2024"),
    ("Sam", "Seller", "https://www.linkedin.com/in/sam/", "", "AcmeCorp", "Sales Director", "05 Jan 2024"),
    ("Blank", "Row", "", "", "", "", "06 Jan 2024"),
]

# Grace and Alan appear in both lists -- the overlap two colleagues have.
# Grace's URL has a trailing slash difference and mixed case, which is the
# kind of thing that defeats naive deduplication.
BOB_ROWS = [
    ("Grace", "Hopper", "https://www.LinkedIn.com/in/grace", "", "Yale", "Research Scientist", "07 Jan 2024"),
    ("Alan", "Turing", "https://www.linkedin.com/in/alan/", "", "NPL", "Group Leader", "08 Jan 2024"),
    ("Barbara", "McClintock", "https://www.linkedin.com/in/barbara/", "", "Cold Spring Harbor", "PI", "09 Jan 2024"),
    ("Dorothy", "Hodgkin", "https://www.linkedin.com/in/dorothy/", "", "Oxford", "Lecturer", "10 Jan 2024"),
    ("Rhonda", "Recruiter", "https://www.linkedin.com/in/rhonda/", "", "HireFast", "Technical Recruiter", "11 Jan 2024"),
]


def _write_export(path: Path, rows) -> None:
    lines = []
    for row in rows:
        buf = []
        writer = csv.writer(_Collector(buf))
        writer.writerow(row)
        lines.append(buf[0].rstrip("\r\n"))
    path.write_text(EXPORT_TEMPLATE.format(rows="\n".join(lines)), encoding="utf-8")


class _Collector:
    """Minimal file-like sink so csv.writer can quote a row for us."""

    def __init__(self, out: list):
        self.out = out

    def write(self, s: str) -> None:
        self.out.append(s)


def main() -> None:
    checks = 0

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        _write_export(tmp / "alice.csv", ALICE_ROWS)
        _write_export(tmp / "bob.csv", BOB_ROWS)

        # --- the preamble ---
        alice = read_export(tmp / "alice.csv", "Alice")
        bob = read_export(tmp / "bob.csv", "Bob")
        assert len(alice) == 6, f"expected 6 of Alice's rows, parsed {len(alice)}"
        assert len(bob) == 5, f"expected 5 of Bob's rows, parsed {len(bob)}"
        assert alice[0].name == "Ada Lovelace"
        assert alice[0].position == "Professor"
        print("ok   LinkedIn's notice preamble is skipped and rows parse")
        checks += 1

        # --- deduplication across admins ---
        people, report = merge({"Alice": alice, "Bob": bob})
        assert report.total_rows == 11
        assert report.unique_people == 9, f"expected 9 unique, got {report.unique_people}"
        assert report.shared == 2, f"expected 2 shared, got {report.shared}"
        print(f"ok   11 rows merged to 9 people, 2 shared ({report.overlap_pct:.0f}% overlap)")
        checks += 1

        grace = next(p for p in people if p.first == "Grace")
        assert sorted(grace.reachable_by) == ["Alice", "Bob"], (
            "Grace's two rows differ in case and trailing slash and should "
            f"still be one person, got {grace.reachable_by}"
        )
        print("ok   URLs differing only in case or trailing slash are one person")
        checks += 1

        # --- connection dates ---
        from .load import Connection

        jan = Connection("A", "B", "", "", "", "10 Jan 2024")
        feb = Connection("C", "D", "", "", "", "02 Feb 2024")
        junk = Connection("E", "F", "", "", "", "sometime")
        assert feb.connected_date > jan.connected_date, (
            "February must sort after January -- the raw strings do not"
        )
        assert junk.connected_date == date.min
        print("ok   connection dates order chronologically, junk sorts oldest")
        checks += 1

        # --- assignment inside the credit pools ---
        for i, person in enumerate(people):
            person.score = 90 - i * 10  # 90, 80, 70, 60, 50, 40, ...
            person.reason = "invented"

        cfg = Config(
            page_name="Test",
            audience="invented brief",
            admins=[Admin("Alice", "alice.csv", 3), Admin("Bob", "bob.csv", 2)],
            target=4,
            per_day=2,
            min_score=55,
            overshoot=1.0,
            exclude_file="already_following.txt",
            model="claude-opus-5",
            effort="low",
            batch_size=40,
        )

        assigned = assign(people, cfg)
        placed = [p for group in assigned.values() for p in group]

        assert len(placed) <= cfg.target, f"placed {len(placed)}, target {cfg.target}"
        for admin in cfg.admins:
            got = len(assigned[admin.name])
            assert got <= admin.credits, f"{admin.name} assigned {got} > {admin.credits} credits"
        print(f"ok   {len(placed)} placed, no admin over their credit pool")
        checks += 1

        for admin_name, group in assigned.items():
            for person in group:
                assert admin_name in person.reachable_by, (
                    f"{person.name} assigned to {admin_name}, who cannot reach them"
                )
        print("ok   nobody is assigned to an admin who cannot reach them")
        checks += 1

        keys = [p.key for p in placed]
        assert len(keys) == len(set(keys)), "someone is in the queue twice"
        print("ok   nobody appears in the queue twice")
        checks += 1

        assert all(p.score >= cfg.min_score for p in placed), "someone below min_score got in"
        print(f"ok   nobody below min_score {cfg.min_score} reached the queue")
        checks += 1

        # --- overshoot: a list deeper than the budget ---
        from dataclasses import replace as _replace

        for person in people:
            person.score = 90  # everyone eligible, so capacity is the only cap

        tight = assign(people, cfg)
        deep = assign(people, _replace(cfg, overshoot=2.0))
        n_tight = sum(len(g) for g in tight.values())
        n_deep = sum(len(g) for g in deep.values())
        assert n_tight == cfg.target, f"at overshoot 1.0 expected {cfg.target}, got {n_tight}"
        assert n_deep > n_tight, (
            f"overshoot 2.0 should emit more rows than 1.0, got {n_deep} vs {n_tight}"
        )
        for admin in cfg.admins:
            assert len(deep[admin.name]) <= int(admin.credits * 2.0)
        print(f"ok   overshoot deepens the list ({n_tight} -> {n_deep} rows) within capacity")
        checks += 1

        # restore the graded scores the later checks rely on
        for i, person in enumerate(people):
            person.score = 90 - i * 10

        # --- excluding people who already follow ---
        from .exclude import apply as apply_exclusion

        excl_file = tmp / "already_following.txt"
        target_person = people[0]
        excl_file.write_text(
            f"# pasted from the page's followers view\n"
            f"{target_person.url}\n"
            f"{people[1].name}, PhD\n"
            f"Someone Not In The List\n",
            encoding="utf-8",
        )
        kept, stats = apply_exclusion(list(people), excl_file)
        assert stats["removed"] == 2, f"expected 2 removed, got {stats['removed']}"
        assert stats["unmatched"] == 1, "a name matching nobody should be reported"
        assert target_person.key not in {k.key for k in kept}
        print("ok   exclusion list drops followers by URL and by name, flags typos")
        checks += 1

        # --- the prompt rows ---
        from .score import _batch_prompt

        tricky = Connection(
            first="Tamar",
            last="Cohen",
            url="",
            company="YEDA - Technology Transfer Company",
            position="Director of Business Development at Yeda, Weizmann Institute",
            connected_on="01 Jan 2024",
        )
        prompt = _batch_prompt([(0, tricky)])
        assert "title: Director of Business Development at Yeda" in prompt
        assert "employer: YEDA - Technology Transfer Company" in prompt
        assert prompt.count("employer:") == 1, "one employer line per person"
        blank = _batch_prompt([(0, Connection("A", "B", "", "", "", ""))])
        assert "(none given)" in blank
        print("ok   prompt rows label title and employer separately")
        checks += 1

        # --- the rule-based scorer ---
        from .rules import score_one

        def conn(position, company):
            return Connection(first="A", last="B", url="", company=company,
                              position=position, connected_on="")

        expectations = [
            (("Professor", "Weizmann Institute of Science"), 80, 100),
            (("PhD Student", "Tel Aviv University"), 80, 100),
            (("Head of Chemistry", "Plastic Back"), 80, 100),
            (("Technical Recruiter", "HireFast"), 0, 24),
            # A recruiter at a research institute is still a recruiter.
            (("Talent Acquisition", "Weizmann Institute of Science"), 0, 24),
            (("Marketing Manager", "Droxi"), 25, 54),
            (("", ""), 0, 24),
        ]
        for (position, company), lo, hi in expectations:
            got, why = score_one(conn(position, company))
            assert lo <= got <= hi, (
                f"{position!r} at {company!r} scored {got}, expected {lo}-{hi} ({why})"
            )
        print(f"ok   rule scorer puts {len(expectations)} known cases in the right band")
        checks += 1

        # --- dates from a non-English export ---
        masked = Connection(first="A", last="B", url="", company="",
                            position="", connected_on="05-???-26")
        older = Connection(first="A", last="B", url="", company="",
                           position="", connected_on="12-???-19")
        assert masked.connected_date == date(2026, 1, 1), (
            "a masked month should degrade to year precision, not be discarded"
        )
        assert masked.connected_date > older.connected_date
        assert Connection(first="A", last="B", url="", company="", position="",
                          connected_on="05-Oct-26").connected_date == date(2026, 10, 5)
        print("ok   masked-month dates keep year precision and still order")
        checks += 1

        # --- the output sheet ---
        out = tmp / "invite_queue.csv"
        written = write(assigned, cfg, out)
        assert written == len(placed)

        rows = list(csv.DictReader(out.open(encoding="utf-8")))
        assert len(rows) == written
        for admin_name, group in assigned.items():
            days = [int(r["day"]) for r in rows if r["admin"] == admin_name]
            expected = [i // cfg.per_day + 1 for i in range(len(group))]
            assert sorted(days) == expected, (
                f"{admin_name} day numbering is {sorted(days)}, expected {expected}"
            )
        print(f"ok   queue written, {cfg.per_day}/day pacing numbered per admin")
        checks += 1

        from .worksheet import write as write_worksheet

        sheets = write_worksheet(assigned, cfg, tmp)
        for admin_name, sheet in sheets.items():
            text = sheet.read_text(encoding="utf-8")
            boxes = text.count("[ ] ")
            assert boxes == len(assigned[admin_name]), (
                f"{admin_name}'s worksheet has {boxes} checkboxes for "
                f"{len(assigned[admin_name])} invites"
            )
            assert "BATCH 1 of" in text
        print(f"ok   worksheets carry one checkbox per invite, batched")
        checks += 1

        shared_in_queue = [r for r in rows if r["also_reachable_by"]]
        for row in shared_in_queue:
            assert row["admin"] not in row["also_reachable_by"]
        print("ok   shared connections note the other admin without duplicating")
        checks += 1

    print(f"\n{checks} checks passed. Nothing was sent and nothing cost anything.")


if __name__ == "__main__":
    main()
