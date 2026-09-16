# Weizmann publications digest

Every Monday morning this sends one email to `bina-members@weizmann.ac.il`
listing the papers published that week by the ~350 Weizmann groups on our
roster, with a paragraph about each one and a few featured at the top.

Nothing runs on anyone's laptop. GitHub runs it on a schedule; if every
machine in the building is off, the email still arrives.

---

## How it works

```
OpenAlex  ──►  match against    ──►  Claude writes a       ──►  email to
(free, no      roster.csv            paragraph per paper        bina-members@
 API key)      (~350 PIs)            + picks the top few
```

1. **OpenAlex** is asked for everything it indexed in the last nine days with a
   Weizmann affiliation. It aggregates Crossref, PubMed, arXiv, bioRxiv and
   most other sources, which is why one query replaces a dozen.
2. Each paper is **matched to our roster**. Papers by Weizmann people we do not
   track are dropped.
3. Anything already sent is **skipped** — `state/seen_works.json` remembers
   every paper that has gone out, so the nine-day window can safely overlap.
4. **Claude reads each abstract and writes one paragraph.** Where OpenAlex has
   no abstract it fetches the paper's page and reads it there.
5. Claude then **picks the few to feature**, reading the paragraphs from step 4.
6. The email goes out and the list of sent papers is committed back.

---

## Setting it up

### 1. The roster — do this first

`roster.csv` is the heart of the thing. One row per PI:

| column | what goes in it |
| --- | --- |
| `name` | `Ada Lovelace` or `Lovelace, Ada` — both work |
| `openalex_author_id` | `A5023888391`. Leave blank and we match by name instead |
| `department` | Becomes a section heading in the email. Spell it consistently |
| `active` | `no` retires someone without deleting their row |
| `notes` | Anything you like; ignored by the code |

Paste your list in with `openalex_author_id` blank and commit it. Then go to
**Actions → Find OpenAlex IDs for the roster → Run workflow**. It looks
everyone up and, when it finishes, offers `roster_resolved.csv` for download
under the run's artifacts. (On your own machine the same thing is
`python -m digest.resolve_roster`.)

That file has a `confidence` column. Open it in Excel,
sort by that column, check everything that is not `high`, then rename the file
over `roster.csv`. Budget an hour. It is the single highest-value hour in this
project: an author ID is exact, whereas a name match can confuse two people
who share a surname and an initial.

### 2. Email

The job needs an SMTP account to send from. Add these under
**Settings → Secrets and variables → Actions → New repository secret**:

| secret | example |
| --- | --- |
| `SMTP_HOST` | `smtp.weizmann.ac.il` |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | the account's username |
| `SMTP_PASSWORD` | its password or app password |
| `SMTP_FROM` | the address the email comes from |

Three options, in the order worth trying:

- **Weizmann's own relay.** Best outcome — mail from a `weizmann.ac.il` address
  will not land in anyone's spam folder. Ask IT for SMTP relay details or a
  service account. Note that many institutions have switched off basic SMTP
  authentication in Microsoft 365, so this may need IT to enable something.
- **A transactional service** (Resend, Brevo, Mailgun). Free at ten recipients
  a week. Needs a verified sending domain.
- **A dedicated Gmail account with an app password.** Works in ten minutes with
  no IT involvement. Tell everyone to mark the first issue "not spam".

### 3. Claude

Add `ANTHROPIC_API_KEY` as a repository secret, from
[console.anthropic.com](https://console.anthropic.com). Without it the digest
still sends, just with no paragraphs and no featured section.

Cost is roughly **$1 per issue** — about a dollar for 60–90 paragraphs, plus a
few cents to pick the features. Set a monthly spend limit in the console if
you want a hard ceiling.

### 4. Try it before it goes live

Go to **Actions → Weekly publications digest → Run workflow**, leave
*"Build the issue but send no email"* ticked, and run it. It builds a real
issue from real data and sends nothing. Download `preview.html` from the run's
artifacts and open it in a browser.

When it looks right, untick the box and run it once more to send for real.
After that it runs itself every Monday.

---

## Everyday use

**Add or remove a PI** — edit `roster.csv`, commit. That is the whole procedure.

**Read an old issue** — every run uploads `preview.html`, `preview.txt` and
`papers.json` as artifacts, kept for 90 days.

**Someone is missing from the email.** In order of likelihood: their row says
`active,no`; their `openalex_author_id` is wrong; their paper is not in
OpenAlex yet (indexing lags by days to weeks — it will appear in a later
issue); or the paper went out in an earlier issue. `papers.json` from the run
shows exactly what was considered.

**Send a catch-up issue** — run the workflow manually with `since` set to a
date. Papers already sent are still skipped, so nobody gets a duplicate.

**Change how it reads** — everything adjustable lives in `config.yaml`:
the lookback window, whether preprints are included, how many papers are
featured, the subject line, the recipients.

---

## Running it on your own machine

Not required — GitHub does this for you — but useful for trying things out.

```bash
pip install -r requirements.txt
python -m digest.selftest            # offline check, no network, free
python -m digest.run --dry-run       # real papers, writes out/preview.html, sends nothing
```

`python -m digest.run --no-summaries` skips Claude entirely: fast, free, and
enough to check that the roster and the layout are behaving.

---

## What this does not do

Worth knowing before someone asks:

- **Preprints and their published versions appear separately.** A bioRxiv
  preprint now and the journal article in six months are two entries. Linking
  them is real work and is not built.
- **OpenAlex indexes on its own schedule.** Papers typically appear within days
  of publication, but some take weeks. This is a digest, not an alert service.
- **Abstracts are missing for some publishers**, Elsevier especially. Claude
  fetches the paper's page for those, which works for open-access papers and
  often fails behind a paywall. Those paragraphs are labelled in the email.
- **Nobody reads the paragraphs before they send.** They are written from the
  abstract by a model, and the email says so. Read the paper before quoting it.
- **Only the ~350 groups in `roster.csv` are covered.** Weizmann papers by
  anyone else are counted in the run log and left out of the email.

---

## The files

| file | what it is |
| --- | --- |
| `config.yaml` | Every setting, commented |
| `roster.csv` | The ~350 PIs |
| `state/seen_works.json` | Papers already sent. Do not edit by hand |
| `digest/openalex.py` | Fetches papers |
| `digest/roster.py` | Decides whose paper it is |
| `digest/summarize.py` | Claude: a paragraph each, then the featured few |
| `digest/render.py` | Builds the email |
| `digest/mailer.py` | Sends it |
| `digest/run.py` | Runs the above in order |
| `digest/resolve_roster.py` | One-time: names → OpenAlex author IDs |
| `digest/selftest.py` | Offline check on invented data |
| `../.github/workflows/weekly-digest.yml` | The Monday schedule |
| `../.github/workflows/resolve-roster.yml` | The roster lookup, run on demand |
