"""Loads config.yaml and the environment settings the pipeline needs."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Config:
    institution_ror: str
    contact_email: str
    lookback_days: int = 9
    max_publication_age_years: int = 2
    highlight_count: int = 5
    max_summaries: int = 150
    summary_concurrency: int = 6
    include_preprints: bool = True
    exclude_types: list[str] = field(default_factory=lambda: ["paratext"])
    allow_name_fallback: bool = True
    recipients: list[str] = field(default_factory=list)
    subject_prefix: str = "Weizmann publications"

    @classmethod
    def load(cls, path: Path | None = None) -> "Config":
        path = path or ROOT / "config.yaml"
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        known = {f for f in cls.__dataclass_fields__}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(
                f"config.yaml has settings I don't recognise: {sorted(unknown)}. "
                "Check for a typo."
            )
        # A bare ROR URL is the form people copy off the website; accept both.
        raw["institution_ror"] = str(raw.get("institution_ror", "")).rstrip("/").split("/")[-1]
        return cls(**raw)


def smtp_settings() -> dict[str, str]:
    """Reads SMTP credentials from the environment (GitHub Actions secrets)."""
    missing = [
        name
        for name in ("SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "SMTP_FROM")
        if not os.environ.get(name)
    ]
    if missing:
        raise RuntimeError(
            "Cannot send email - these secrets are not set: "
            + ", ".join(missing)
            + ". See README.md, section 'Setting up email'."
        )
    return {
        "host": os.environ["SMTP_HOST"],
        "port": int(os.environ.get("SMTP_PORT", "587")),
        "user": os.environ["SMTP_USER"],
        "password": os.environ["SMTP_PASSWORD"],
        "sender": os.environ["SMTP_FROM"],
    }
