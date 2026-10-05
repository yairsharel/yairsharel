"""Claude scores each connection against the audience brief in config.yaml.

Only two fields per person survive LinkedIn's export -- company and job
title -- so that is all the model gets. It is not asked to guess at anything
it cannot see.
"""

import json

import anthropic

from .config import Config
from .load import Connection

# Per million tokens, input/output. Only used to print what a run cost.
PRICES = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

SCHEMA = {
    "type": "object",
    "properties": {
        "scores": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "i": {"type": "integer"},
                    "score": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": ["i", "score", "reason"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["scores"],
    "additionalProperties": False,
}

SYSTEM = """\
You are ranking a page admin's LinkedIn connections by how well each one fits \
the audience the page wants to reach. Each invite spends a credit that only \
comes back if the person accepts, so a generous score is not a kindness.

The page is {page_name}. Here is the audience brief, written by the page owner:

{audience}

You will get a numbered list of connections. Each gives a job title and an \
employer, and nothing else -- that is genuinely all the export contains. \
Score each one 0-100 on fit with the brief:

  80-100  clearly in the audience the brief describes
  55-79   plausibly in it; the title or employer points the right way
  25-54   probably not, but not obviously wrong
  0-24    clearly outside it, or the row is too empty to judge

Give a reason of at most twelve words, citing what in the title or employer \
drove the score. Where a row is blank or uninformative, score it low and say \
so rather than inventing a profession for them.

Return one entry per connection, keeping the index you were given.\
"""


def _batch_prompt(batch: list[tuple[int, Connection]]) -> str:
    lines = []
    for i, conn in batch:
        title = conn.position or "(no title given)"
        company = conn.company or "(no employer given)"
        lines.append(f"{i}. {title} at {company}")
    return "Score these connections:\n\n" + "\n".join(lines)


def score_all(people: list[Connection], cfg: Config, verbose: bool = True) -> None:
    """Fills in .score and .reason on each connection, in place.

    A batch that fails leaves its people unscored rather than taking the run
    down with it; they sort to the bottom of the queue and are visible in the
    output as blank scores.
    """
    client = anthropic.Anthropic()
    indexed = list(enumerate(people))
    batches = [
        indexed[i : i + cfg.batch_size]
        for i in range(0, len(indexed), cfg.batch_size)
    ]

    system = SYSTEM.format(page_name=cfg.page_name, audience=cfg.audience)
    in_tokens = out_tokens = 0
    failed = 0

    for n, batch in enumerate(batches, 1):
        if verbose:
            print(f"  scoring batch {n}/{len(batches)} ({len(batch)} people)...")
        try:
            response = client.messages.create(
                model=cfg.model,
                max_tokens=8000,
                # The brief is identical on every request, so cache it.
                system=[
                    {
                        "type": "text",
                        "text": system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": _batch_prompt(batch)}],
                output_config={"effort": cfg.effort, "format": {"type": "json_schema", "schema": SCHEMA}},
            )
        except anthropic.NotFoundError:
            raise SystemExit(
                f"the API does not recognise model {cfg.model!r}. Check "
                f"scoring.model in config.yaml"
            )
        except anthropic.AuthenticationError:
            raise SystemExit(
                "the API rejected the credentials. Set ANTHROPIC_API_KEY, or run "
                "without scoring: python -m invites.run --no-scoring"
            )
        except anthropic.RateLimitError:
            print(f"  ! batch {n} gave up against the rate limit; left unscored")
            failed += len(batch)
            continue
        except (anthropic.APIStatusError, anthropic.APIConnectionError) as exc:
            print(f"  ! batch {n} failed ({type(exc).__name__}); left unscored")
            failed += len(batch)
            continue

        in_tokens += response.usage.input_tokens
        out_tokens += response.usage.output_tokens

        # output_config.format guarantees the first text block is valid JSON.
        text = next(b.text for b in response.content if b.type == "text")
        by_index = {person_i: conn for person_i, conn in batch}
        for entry in json.loads(text)["scores"]:
            conn = by_index.get(entry["i"])
            if conn is not None:
                conn.score = max(0, min(100, int(entry["score"])))
                conn.reason = entry["reason"].strip()

    if verbose:
        rate_in, rate_out = PRICES.get(cfg.model, (0.0, 0.0))
        cost = in_tokens / 1e6 * rate_in + out_tokens / 1e6 * rate_out
        print(
            f"  scored {len(people) - failed} of {len(people)} "
            f"({in_tokens:,} in / {out_tokens:,} out tokens"
            + (f", about ${cost:.2f})" if cost else ")")
        )
        if failed:
            print(f"  {failed} left unscored -- they sort last, with a blank score")
