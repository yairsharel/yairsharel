# LinkedIn page invite queue

A LinkedIn page cannot ask strangers to follow it. What it can do is let each
page admin invite their own 1st-degree connections, spending from a monthly
pool of invite credits. This turns two admins' connection exports into one
ranked, deduplicated, paced queue of who to invite and in what order.

The sending is still done by hand, in LinkedIn's own panel. That is on
purpose: automating the clicks violates §8.2 of LinkedIn's User Agreement and
risks the admin account, and it would save about twenty minutes, because the
credit ceiling is enforced server-side either way.

---

## How it works

```
two connections   ──►  merge and      ──►  Claude scores   ──►  assign to an
exports (CSV)          deduplicate         each 0-100 vs        admin within
                       across admins       the brief            their credits
                                                                     │
                                                                     ▼
                                                            out/invite_queue.csv
                                                            + a worksheet to
                                                              click from
```

1. Each admin's **connections export** is read. The downloaded file opens with
   notice text before the real header, which is why handing it to a plain CSV
   reader gets you nothing.
2. The two lists are **merged on profile URL**. Two colleagues at one
   institute typically share 10–25% of their connections, and inviting
   someone twice spends two credits to annoy one person.
3. **Claude scores everyone 0–100** against the audience brief in
   `config.yaml`, with a short reason.
4. Each person is **assigned to one admin** who can actually reach them,
   inside that admin's credit balance.
5. The queue is written in **batches**, with a plain-text worksheet per
   admin to work through while clicking.

---

## The credit model, because it drives everything

Credits are **per admin**, not pooled across the page — each admin's panel
shows their own balance. Two admins with 300 and 250 have 550 between them.

A credit is **returned when the invite is accepted**. That compounds, so the
acceptance rate decides what the budget is worth far more than the budget
does. Sending from `C` credits at acceptance rate `r` yields about
`r·C/(1−r)` followers:

| acceptance rate | invites you get to send | followers, from 550 credits |
| --- | --- | --- |
| 20% | ~690 | ~140 |
| 30% | ~790 | ~235 |
| 40% | ~920 | ~370 |

So **250 followers from 550 credits needs roughly a one-in-three acceptance
rate.** Below that the budget runs out first. This is the whole reason for
the checkpoint below, and the reason the page should have recent posts on it
before the first invite goes out.

Verify the refund behaviour on your first batch rather than taking the table
on faith — watch whether the balance ticks back up as invites are accepted.

---

## Setting it up

### 1. The exports

Each admin: **Settings & Privacy → Data Privacy → Get a copy of your data**,
tick **Connections** only, request the archive. It arrives by email in about
ten minutes, occasionally up to a day.

Drop the CSVs in `connections/` under the names in `config.yaml`. Do not open
and re-save them first — the loader handles LinkedIn's format as downloaded.

**These files stay out of git.** `connections/` and `out/` are gitignored
down to the directory, because both hold names, employers, job titles and
sometimes email addresses for several hundred real people. Nothing in here
needs to be committed for the tool to work, and for an institutional page
there are good reasons that data should not end up in a repository.

### 2. The brief

`page.audience` in `config.yaml` is the setting that determines whether any
of this works. It is what Claude scores against.

The one real constraint: the export gives you each person's **company and job
title and nothing else** — no field, no location, no interests. Write the
brief in terms that can be judged from those two fields, or the scores will
be noise dressed up as numbers.

### 3. The credits

Put each admin's real balance in `config.yaml`, read from their **Invite
connections** panel on the day you run this. The pool refreshes monthly.

### 4. Try it before spending anything

```bash
pip install -r requirements.txt
python -m invites.selftest              # offline, invented data, free
python -m invites.run --no-scoring      # real exports, no Claude, free
```

`--no-scoring` loads the exports, merges them and builds the queue ordered by
connection date instead of fit. It tells you the two things worth knowing
before spending anything: that the files parsed, and how much the two lists
overlap.

Then run it for real:

```bash
export ANTHROPIC_API_KEY=...
python -m invites.run
```

---

## Sending

Open the page's admin view → **Invite connections**. Sending is a loop:
paste a name from `out/worksheet_<admin>.txt` into that panel's search box,
tick the checkbox, send the batch. Record what you sent in the `status`
column of `invite_queue_<admin>.csv` — nothing here tracks it for you, and
that column is what makes a second run skip people you already invited.

Budget roughly **10–20 seconds per person**, so 300 invites is about an hour
and a half of clicking. There is no CSV import and no API for this; the
panel is the only route.

### On pacing

The batch size is not a LinkedIn rate limit. The credit pool is the only
hard cap, and there is no documented per-day throttle on page invites.
Batching buys exactly one thing, and it is worth having:

**Send batch 1, then wait about 48 hours before the rest.** A credit comes
back only if the invite is accepted, so a wrong audience brief burns
credits permanently. Finding that out after 50 invites costs you ~42
credits; finding out after 300 costs you 250. Under about 20% acceptance,
stop and revise `page.audience` rather than pressing on.

After that checkpoint, go as fast as you like. Speed actually helps:
refunded credits re-enter the pool, so a good brief sent quickly lets you
send more within the month. Set `per_day` to the full target if you want
the remainder in one sitting.

### People who already follow

They cannot be invited, and nothing in the data tells us who they are in
advance, so there are two mitigations and you want both.

**Paste them in.** Copy the names into
`connections/already_following.txt`, re-run. Every name there is a search
you do not have to waste.

Note which source you use. The page's **followers XLS export** is no help:
its six sheets are daily counts plus demographic breakdowns (location, job
function, seniority, industry, company size) and it contains no member
names or profile URLs at all — verified by searching every cell of a real
one. Names, where they are available, come from the Followers view in the
admin UI, by hand.

**The list runs deep.** `queue.overshoot` makes the worksheet longer than
your credit balance — 1.8× by default — so you can reach your budget even
with no exclusion list at all. Work in order and **stop when you have sent
your credit count**, not at the end of the list.

Record `already following` against those rows in the CSV. That rate is the
one number that tells you what `overshoot` should be next month, and it is
not recoverable once the sitting is over.

### If both admins are sending

A worksheet row marked `[also reachable by ...]` is someone both admins
know. They are assigned to one of you here, and only that person should
send it — a duplicate invite spends two credits to reach one person. Work
your own file only.

## What it costs

Scoring is cheap enough not to think about. Measured on a real 824-connection
export: **about $0.72** on `claude-opus-5`, and roughly a fifth of that on
`claude-haiku-4-5`, which is a one-line change in `config.yaml`. At the size
of two people's connection lists the model choice is not a budget decision,
so the default is the more capable one. The run prints what it actually spent.

Invite credits themselves are free. The only path here that costs real money
is LinkedIn Follower Ads, which this tool does not touch.

---

## What this does not do

- **It does not send anything.** By design, see the top of this file.
  Scripting the invite panel is what LinkedIn's §8.2 prohibits, and the
  cost of being caught falls on the admin account, which is the page's
  access. The legitimate way to cut the work is fewer searches, not
  automated clicks: run with `--by-employer` and, if the panel offers a
  company filter, each heading becomes one filter instead of N searches.
  How much that helps depends entirely on the list — one of ours collapsed
  to a single employer covering the whole budget, the other had 90% of its
  employers appearing exactly once.
- **It cannot discover who already follows the page.** LinkedIn's API
  returns follower *statistics* — counts by seniority, function, industry —
  never a member list, and no data export contains one. You have to paste
  the names in yourself from the page's Followers view, into
  `connections/already_following.txt`. Until you do, the worksheet runs
  deeper than your credits — `queue.overshoot` as a multiplier, or an exact
  `list_size` per admin — so you can still reach your budget by skipping
  followers as you hit them. The only mechanism that filters on
  this automatically is audience exclusion in Campaign Manager, the paid
  path.
- **It only reaches your admins' connections.** That is the feature's
  boundary, not this tool's. Growing past it means adding admins with
  relevant connections, or paying for reach.
- **It scores from a job title and an employer.** Someone whose title is
  uninformative scores low whether or not they would have been interested.
- **It does not remember previous runs.** Keep the `status` column.
- **The assignment is greedy, not optimal.** With two admins and a target
  well under the combined credits that is noise; pushing the target close to
  the ceiling could leave a few placeable people unplaced.

---

## The files

| file | what it is |
| --- | --- |
| `config.yaml` | Every setting, commented. The audience brief lives here |
| `connections/` | The exports, as downloaded. Gitignored |
| `connections/already_following.txt` | Followers to exclude, pasted by hand |
| `out/invite_queue.csv` | What the admins work from. Gitignored |
| `invites/load.py` | Reads LinkedIn's export, preamble and all |
| `invites/assign.py` | Merges the lists, then picks who invites whom |
| `invites/score.py` | Claude: a score and a reason each |
| `invites/queue.py` | Writes the sheet |
| `invites/run.py` | Runs the above in order |
| `invites/exclude.py` | Drops people who already follow the page |
| `invites/rules.py` | Rule-based scorer, for when there is no API key |
| `invites/worksheet.py` | The plain-text list you click from, by fit or by employer |
| `invites/selftest.py` | Offline check on invented data |
