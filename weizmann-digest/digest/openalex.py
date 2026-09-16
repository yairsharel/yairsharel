"""Fetches Weizmann-affiliated works from OpenAlex.

OpenAlex is free and needs no API key. We identify ourselves with a contact
address (the "polite pool"), which gets us faster, more reliable service.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Iterator

import requests

log = logging.getLogger(__name__)

API = "https://api.openalex.org/works"

# Only ask for the fields we actually render. Keeps responses ~10x smaller.
FIELDS = ",".join(
    [
        "id",
        "doi",
        "title",
        "publication_date",
        "publication_year",
        "type",
        "primary_location",
        "open_access",
        "authorships",
        "cited_by_count",
        "abstract_inverted_index",
        "primary_topic",
    ]
)

PREPRINT_SOURCES = {
    "arxiv",
    "biorxiv",
    "medrxiv",
    "chemrxiv",
    "research square",
    "ssrn",
    "preprints.org",
}


@dataclass
class Work:
    id: str
    title: str
    doi: str | None
    url: str
    published: str
    year: int | None
    work_type: str
    journal: str
    is_preprint: bool
    is_open_access: bool
    citations: int
    topic: str | None
    abstract: str | None
    authors: list[dict[str, Any]]

    @property
    def short_id(self) -> str:
        return self.id.rsplit("/", 1)[-1]


def _decode_abstract(inverted: dict[str, list[int]] | None) -> str | None:
    """OpenAlex stores abstracts as {word: [positions]}. Put them back in order."""
    if not inverted:
        return None
    positions: list[tuple[int, str]] = []
    for word, spots in inverted.items():
        positions.extend((spot, word) for spot in spots)
    if not positions:
        return None
    positions.sort()
    return " ".join(word for _, word in positions)


def _parse(raw: dict[str, Any]) -> Work:
    location = raw.get("primary_location") or {}
    source = location.get("source") or {}
    journal = source.get("display_name") or "Unpublished / no source listed"

    work_type = raw.get("type") or "unknown"
    is_preprint = work_type == "preprint" or journal.lower() in PREPRINT_SOURCES

    doi = raw.get("doi")
    url = doi or location.get("landing_page_url") or raw["id"]

    topic = (raw.get("primary_topic") or {}).get("display_name")

    return Work(
        id=raw["id"],
        title=raw.get("title") or "(untitled)",
        doi=doi,
        url=url,
        published=raw.get("publication_date") or "",
        year=raw.get("publication_year"),
        work_type=work_type,
        journal=journal,
        is_preprint=is_preprint,
        is_open_access=bool((raw.get("open_access") or {}).get("is_oa")),
        citations=raw.get("cited_by_count") or 0,
        topic=topic,
        abstract=_decode_abstract(raw.get("abstract_inverted_index")),
        authors=raw.get("authorships") or [],
    )


def fetch_recent(
    ror: str,
    contact_email: str,
    since: date,
    session: requests.Session | None = None,
) -> Iterator[Work]:
    """Yields every work OpenAlex *indexed* on or after `since` for this institution.

    We filter on when OpenAlex created the record, not on publication date. A
    paper that appears in OpenAlex three weeks after it was published is still
    news to us the week we first see it, and filtering on publication date
    would silently drop it.
    """
    session = session or requests.Session()
    cursor = "*"
    page = 0

    while cursor:
        params = {
            "filter": f"authorships.institutions.ror:{ror},from_created_date:{since.isoformat()}",
            "select": FIELDS,
            "per-page": "200",
            "cursor": cursor,
            "mailto": contact_email,
        }
        response = _get_with_retry(session, params)
        payload = response.json()

        page += 1
        results = payload.get("results", [])
        log.info("OpenAlex page %d: %d works", page, len(results))

        for raw in results:
            yield _parse(raw)

        cursor = (payload.get("meta") or {}).get("next_cursor")
        if not results:
            break


def _get_with_retry(
    session: requests.Session, params: dict[str, str], attempts: int = 4
) -> requests.Response:
    """OpenAlex occasionally rate-limits or hiccups. Back off and try again."""
    delay = 2.0
    last_error: Exception | None = None

    for attempt in range(1, attempts + 1):
        try:
            response = session.get(API, params=params, timeout=90)
            if response.status_code == 429 or response.status_code >= 500:
                raise requests.HTTPError(
                    f"OpenAlex returned {response.status_code}", response=response
                )
            response.raise_for_status()
            return response
        except (requests.RequestException, requests.HTTPError) as exc:
            last_error = exc
            if attempt == attempts:
                break
            log.warning(
                "OpenAlex request failed (attempt %d/%d): %s - retrying in %.0fs",
                attempt, attempts, exc, delay,
            )
            time.sleep(delay)
            delay *= 2

    raise RuntimeError(f"OpenAlex is not responding after {attempts} attempts") from last_error


def default_since(lookback_days: int, today: date | None = None) -> date:
    return (today or date.today()) - timedelta(days=lookback_days)
