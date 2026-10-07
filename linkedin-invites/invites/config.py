"""Loads config.yaml and checks it says something usable."""

from dataclasses import dataclass
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


@dataclass
class Admin:
    name: str
    export: str
    credits: int

    # How many rows to put in front of this admin. Larger than `credits`
    # because people who already follow the page cannot be invited and
    # LinkedIn will not say who they are in advance. None means fall back
    # to the queue-wide overshoot multiplier.
    list_size: int | None = None

    def rows(self, overshoot: float) -> int:
        return self.list_size or int(self.credits * overshoot)

    @property
    def export_path(self) -> Path:
        return ROOT / "connections" / self.export


@dataclass
class Config:
    page_name: str
    audience: str
    admins: list[Admin]
    target: int
    per_day: int
    min_score: int
    overshoot: float
    exclude_file: str
    model: str
    effort: str
    batch_size: int

    @property
    def total_credits(self) -> int:
        return sum(a.credits for a in self.admins)

    @property
    def exclude_path(self) -> Path:
        return ROOT / "connections" / self.exclude_file


def load(path: Path | None = None) -> Config:
    path = path or ROOT / "config.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))

    page = raw.get("page") or {}
    queue = raw.get("queue") or {}
    scoring = raw.get("scoring") or {}

    admins = [
        Admin(
            name=a["name"],
            export=a["export"],
            credits=int(a["credits"]),
            list_size=int(a["list_size"]) if a.get("list_size") else None,
        )
        for a in raw.get("admins") or []
    ]
    if not admins:
        raise ValueError("config.yaml lists no admins, so there is nobody to send invites")

    audience = (page.get("audience") or "").strip()
    if not audience:
        raise ValueError(
            "page.audience is empty. It is the brief every connection gets scored "
            "against -- without it the ranking is meaningless"
        )

    cfg = Config(
        page_name=page.get("name") or "our page",
        audience=audience,
        admins=admins,
        target=int(queue.get("target", 250)),
        per_day=int(queue.get("per_day", 25)),
        min_score=int(queue.get("min_score", 55)),
        overshoot=float(queue.get("overshoot", 1.8)),
        exclude_file=raw.get("exclude_file") or "already_following.txt",
        model=scoring.get("model", "claude-opus-5"),
        effort=scoring.get("effort", "low"),
        batch_size=int(scoring.get("batch_size", 40)),
    )

    if cfg.overshoot < 1.0:
        raise ValueError("queue.overshoot below 1.0 would emit fewer rows than credits")

    if cfg.target > cfg.total_credits:
        raise ValueError(
            f"queue.target is {cfg.target} but the admins hold {cfg.total_credits} "
            f"credits between them"
        )
    return cfg
