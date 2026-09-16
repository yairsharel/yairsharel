"""Writes a paragraph about every paper, then picks the few to feature.

Two passes, in this order:

  1. `summarize_all` reads each abstract and writes one paragraph. Papers are
     handled one at a time, concurrently, so a failure on one paper costs us
     that paragraph and nothing else.
  2. `choose_featured` reads the paragraphs from pass 1 and picks the few that
     lead the issue. It sees the summaries rather than raw abstracts, so it is
     cheap and it never contradicts what the newsletter already says.

OpenAlex has no abstract for a meaningful share of papers - Elsevier titles in
particular - so Claude is given the paper's URL and may fetch the page when the
abstract is missing.
"""

from __future__ import annotations

import json
import logging
import os
import textwrap
from concurrent.futures import ThreadPoolExecutor

log = logging.getLogger(__name__)

MODEL = "claude-opus-5"

SUMMARY_SYSTEM = textwrap.dedent(
    """
    You write one-paragraph summaries of new scientific papers for an internal
    Weizmann Institute newsletter. Your readers are a small scientific
    communications team: scientifically literate, but almost never specialists
    in the field of the paper in front of them.

    Write exactly one paragraph, 60-90 words. Lead with what the researchers
    actually found or built, then give the reader one sentence on why it
    matters or what it enables. Plain scientific English: no jargon a first-year
    graduate student in another discipline would not know, no "researchers
    investigated" throat-clearing, no hype, and no adjectives the abstract does
    not earn.

    Accuracy outranks readability. Never state a finding the source text does
    not support, never invent numbers, organisms, mechanisms or applications,
    and never guess at content from the title alone. If you were given no
    abstract and could not fetch the page, say in one sentence what the paper
    appears to be about from its title and venue, and set `based_on` to
    "title_only" - that is a correct answer, not a failure.
    """
).strip()

SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "paragraph": {"type": "string"},
        "based_on": {"type": "string", "enum": ["abstract", "fetched_page", "title_only"]},
    },
    "required": ["paragraph", "based_on"],
    "additionalProperties": False,
}

FEATURE_SYSTEM = textwrap.dedent(
    """
    You choose which of this week's Weizmann papers lead an internal
    newsletter. Choose for interest across a mixed scientific audience: a
    result that is striking, unusually broad in reach, methodologically
    notable, or likely to draw outside attention. Do not rank by journal name -
    a genuinely surprising result in a specialist journal beats a routine one
    in a famous journal. Prefer a spread across fields over several papers from
    one area. Give a short reason, for the editors rather than the readers,
    that says what makes each one worth leading with.
    """
).strip()

FEATURE_SCHEMA = {
    "type": "object",
    "properties": {
        "featured": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "index": {"type": "integer"},
                    "why_featured": {"type": "string"},
                },
                "required": ["index", "why_featured"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["featured"],
    "additionalProperties": False,
}


def _client():
    """Returns an Anthropic client, or None if we cannot summarize this run."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        log.warning("ANTHROPIC_API_KEY is not set - the digest will go out without summaries")
        return None
    try:
        import anthropic
    except ImportError:
        log.warning("The `anthropic` package is not installed - skipping summaries")
        return None
    # Summaries run in parallel, so let the SDK ride out rate limiting itself.
    return anthropic.Anthropic(max_retries=5)


def _json_reply(response) -> dict | None:
    if response.stop_reason == "refusal":
        log.warning("Claude declined to answer")
        return None
    text = next((b.text for b in response.content if b.type == "text"), None)
    return json.loads(text) if text else None


def _summarize_one(client, item: dict, allow_fetch: bool) -> dict | None:
    work = item["work"]
    abstract = work.abstract

    if abstract:
        source = f"Abstract:\n{abstract[:6000]}"
        instruction = "Summarize this paper from its abstract."
    elif allow_fetch:
        source = "Abstract: not available from OpenAlex."
        instruction = (
            f"No abstract is available. Fetch {work.url} and summarize the paper from "
            f"the abstract on that page. If the page cannot be fetched or is behind a "
            f"paywall with no abstract shown, fall back to `title_only`."
        )
    else:
        source = "Abstract: not available."
        instruction = "No abstract is available and fetching is disabled, so use `title_only`."

    prompt = textwrap.dedent(
        f"""
        Title: {work.title}
        Journal / source: {work.journal}{" (preprint)" if work.is_preprint else ""}
        Field: {work.topic or "unclassified"}
        Weizmann authors: {", ".join(p.name for p in item["people"]) or "not matched to our roster"}
        Link: {work.url}

        {source}

        {instruction}
        """
    ).strip()

    request: dict = {
        "model": MODEL,
        "max_tokens": 8000,
        "system": SUMMARY_SYSTEM,
        "thinking": {"type": "adaptive"},
        "output_config": {"effort": "low", "format": {"type": "json_schema", "schema": SUMMARY_SCHEMA}},
        "messages": [{"role": "user", "content": prompt}],
    }
    if allow_fetch and not abstract:
        request["tools"] = [
            {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 2}
        ]

    try:
        return _json_reply(client.messages.create(**request))
    except Exception as exc:
        log.warning("Could not summarize %r: %s", work.title[:60], exc)
        return None


def summarize_all(
    items: list[dict], concurrency: int = 6, allow_fetch: bool = True, limit: int = 150
) -> list[dict]:
    """Attaches a `summary` paragraph to each item, in place. Returns the list."""
    client = _client()
    if client is None or not items:
        return items

    if len(items) > limit:
        log.warning(
            "%d papers this week, above the %d-paper cap - summarizing the %d most recent",
            len(items), limit, limit,
        )
        targets = sorted(items, key=lambda i: i["work"].published, reverse=True)[:limit]
    else:
        targets = items

    log.info("Summarizing %d papers (%d at a time)", len(targets), concurrency)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        results = pool.map(lambda item: _summarize_one(client, item, allow_fetch), targets)

        for item, result in zip(targets, results):
            if not result:
                continue
            item["summary"] = result["paragraph"]
            item["based_on"] = result["based_on"]

    written = sum(1 for i in items if i.get("summary"))
    thin = sum(1 for i in items if i.get("based_on") == "title_only")
    log.info("Wrote %d summaries (%d from the title alone - no abstract found)", written, thin)
    return items


def choose_featured(items: list[dict], count: int) -> list[dict]:
    """Picks the papers to lead the issue, reading the summaries from pass one."""
    summarized = [i for i in items if i.get("summary")]
    if not summarized or count <= 0:
        return []

    client = _client()
    if client is None:
        return []

    count = min(count, len(summarized))
    catalogue = "\n\n".join(
        f"[{n}] {i['work'].title}\n"
        f"    {i['work'].journal}{' (preprint)' if i['work'].is_preprint else ''}\n"
        f"    {i['summary']}"
        for n, i in enumerate(summarized)
    )
    prompt = (
        f"Here are this week's {len(summarized)} Weizmann papers, each with the "
        f"summary that will appear in the newsletter.\n\n{catalogue}\n\n"
        f"Pick the {count} to lead the issue, most compelling first. Refer to each "
        f"by its [index] number."
    )

    try:
        payload = _json_reply(
            client.messages.create(
                model=MODEL,
                max_tokens=8000,
                system=FEATURE_SYSTEM,
                thinking={"type": "adaptive"},
                output_config={"format": {"type": "json_schema", "schema": FEATURE_SCHEMA}},
                messages=[{"role": "user", "content": prompt}],
            )
        )
    except Exception as exc:
        log.warning("Could not choose featured papers (%s) - the issue will have no lead section", exc)
        return []

    if not payload:
        return []

    chosen: list[dict] = []
    for entry in payload.get("featured", []):
        index = entry.get("index")
        if not isinstance(index, int) or not 0 <= index < len(summarized):
            log.warning("Claude referenced paper [%s], which does not exist - skipping", index)
            continue
        item = summarized[index]
        item["why_featured"] = entry["why_featured"]
        chosen.append(item)

    log.info("Featured %d papers", len(chosen))
    return chosen
