"""A rule-based scorer, for when there is no API key to hand.

This encodes the same bands as the brief in config.yaml, in explicit
regexes instead of a model's judgement. The trade is honest: rules are
free, instant, reproducible and auditable, and they cannot read a title
they were not told about. "Head of Translational Pipelines" means
something to a model and nothing to a regex.

Use it to get a defensible list without an API key, or to sanity-check
what the model pass produced. `invites.score` is the better scorer when a
key is available.
"""

import re

from .load import Connection

W = lambda *alts: re.compile(r"\b(" + "|".join(alts) + r")\b", re.I)

# Weizmann, Bina, and the tech transfer arm. The brief puts these at the top
# whatever the person's title.
HOME = W(r"weizmann", r"bina\b", r"yeda")

# Universities, institutes, hospitals, research centres -- Israeli ones seen
# in these two exports, plus the generic words that catch the rest.
ACADEMIC = W(
    r"universit\w*", r"technion", r"college", r"institute", r"instit\w*",
    r"hospital", r"medical cent\w*", r"medical center", r"school of",
    r"faculty", r"academy", r"academia", r"max planck", r"cnrs", r"embl",
    r"volcani", r"davidson", r"sheba", r"hadassah", r"ichilov", r"rambam",
    r"migal", r"agricultural research", r"national lab\w*",
)

# Companies whose business is research, so an unclear title there is still
# probably science-adjacent.
RESEARCH_CO = W(
    r"bio\w*", r"pharma\w*", r"therapeutic\w*", r"medtech", r"diagnostic\w*",
    r"genom\w*", r"laborator\w*", r"labs?", r"teva", r"novocure", r"medical",
    r"health\w*", r"clinical", r"chemical\w*", r"materials", r"semiconductor",
)

RESEARCH_TITLE = W(
    r"professor", r"prof", r"principal investigator", r"\bpi\b",
    r"group leader", r"lab head", r"head of lab\w*", r"lecturer",
    r"post-?doc\w*", r"postdoctoral", r"phd", r"doctoral", r"ph\.d",
    r"research\w*", r"scientist", r"research fellow", r"staff scientist",
    r"academic", r"faculty",
)

INDUSTRY_RD = W(
    r"founder", r"co-?founder", r"ceo", r"cto", r"cso", r"chief scien\w*",
    r"chief techn\w*", r"chief medical", r"vp r&d", r"vp of r&d",
    r"head of r&d", r"head of research", r"head of chemistry",
    r"head of biolog\w*", r"head of development", r"r&d manager",
    r"r&d director", r"director of r&d", r"svp", r"cmo",
)

TRANSLATION = W(
    r"technology transfer", r"tech transfer", r"business development",
    r"innovation", r"venture\w*", r"incubator", r"accelerator",
    r"programme officer", r"program officer", r"editor", r"journalist",
    r"science communicat\w*", r"grants?", r"entrepreneur\w*",
)

TECHNICAL = W(
    r"data scientist", r"data analyst", r"bioinformatic\w*",
    r"computational", r"machine learning", r"\bml\b", r"algorithm\w*",
    r"software", r"engineer\w*", r"analyst", r"chemist", r"biologist",
    r"physicist", r"statistician", r"developer",
)

LEADERSHIP = W(
    r"director", r"head of", r"vp", r"vice president", r"president",
    r"partner", r"manager", r"chair\w*", r"c-?level", r"coo", r"cfo",
)

NEGATIVE = W(
    r"recruit\w*", r"talent acquisition", r"headhunter", r"sourcer",
    r"account executive", r"account manager", r"sales", r"realtor",
    r"real estate", r"insurance", r"mortgage", r"travel agent",
)

# Small adjustments, so a thousand Weizmann people do not all tie.
SENIOR = W(r"senior", r"principal", r"lead", r"chief", r"head", r"professor",
           r"group leader", r"director")
DOMAIN = W(r"biolog\w*", r"chemi\w*", r"physic\w*", r"neuro\w*", r"genom\w*",
           r"immuno\w*", r"molecular", r"cell\w*", r"protein", r"cancer",
           r"oncolog\w*", r"comput\w*", r"data", r"material\w*", r"quantum",
           r"climate", r"plant", r"microbiol\w*", r"structural")
SUPPORT = W(r"assistant", r"coordinator", r"secretar\w*", r"administrat\w*",
            r"receptionist", r"intern\b", r"student")


def score_one(conn: Connection) -> tuple[int, str]:
    title = conn.position or ""
    employer = conn.company or ""

    if not title and not employer:
        return 5, "no title and no employer; nothing to judge"

    # A recruiter at a university is still a recruiter.
    if NEGATIVE.search(title) and not RESEARCH_TITLE.search(title):
        return 15, "recruiting or non-technical sales role"

    home = bool(HOME.search(employer))
    academic = bool(ACADEMIC.search(employer))
    research_co = bool(RESEARCH_CO.search(employer))

    if home:
        base, why = 88, "at Weizmann, Bina or Yeda"
    elif academic:
        base, why = 85, "at a university, institute or hospital"
    elif RESEARCH_TITLE.search(title):
        base, why = 84, "research role"
    elif INDUSTRY_RD.search(title):
        base, why = 83, "science or R&D leadership"
    elif TRANSLATION.search(title):
        base, why = 80, "translation, innovation or communication role"
    elif TECHNICAL.search(title):
        base, why = 78, "technical or scientific role"
    elif research_co:
        base, why = 64, "at a research-driven company, title unclear"
    elif LEADERSHIP.search(title):
        base, why = 44, "leadership role, no visible science link"
    else:
        base, why = 34, "no visible research or science link"

    bonus = 0
    if base >= 78:
        if RESEARCH_TITLE.search(title):
            bonus += 4
            why += "; research title"
        elif INDUSTRY_RD.search(title):
            bonus += 3
            why += "; R&D leadership"
        if SENIOR.search(title):
            bonus += 2
        if DOMAIN.search(title):
            bonus += 2
        if SUPPORT.search(title):
            bonus -= 6
            why += "; support or student role"
        if not title:
            bonus -= 4
            why += "; no title given"

    return max(0, min(100, base + bonus)), why


def score_all(people: list[Connection], verbose: bool = True) -> None:
    for conn in people:
        conn.score, conn.reason = score_one(conn)
    if verbose:
        from collections import Counter
        bands = Counter(
            "80-100" if p.score >= 80 else
            "55-79" if p.score >= 55 else
            "25-54" if p.score >= 25 else "0-24"
            for p in people
        )
        print(f"  scored {len(people):,} by rule, no API call and no cost")
        for band in ("80-100", "55-79", "25-54", "0-24"):
            n = bands.get(band, 0)
            print(f"    {band:7} {n:6,}  ({100*n/len(people):.0f}%)")
