"""Central configuration for CreditLens AI.

Every generated dataset depends only on SEED and the sizes below, so the whole
data folder can be deleted and rebuilt identically at any time.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv() -> None:
    """Minimal .env loader so the project needs no extra dependency."""
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


@dataclass(frozen=True)
class Paths:
    root: Path = REPO_ROOT
    data: Path = REPO_ROOT / "data"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def clean(self) -> Path:
        return self.data / "clean"

    @property
    def curated(self) -> Path:
        return self.data / "curated"

    @property
    def answer_key(self) -> Path:
        """Instructor-only truth. Never give this folder to workshop pods."""
        return self.data / "answer_key"

    def with_data_root(self, data_root: Path) -> "Paths":
        return Paths(root=self.root, data=Path(data_root))


@dataclass(frozen=True)
class Sizes:
    companies: int = 40
    applications: int = 30
    statement_months: int = 12
    related_party_groups: int = 4
    scanned_financials_share: float = 0.25
    statement_pdfs: int = 6
    loan_history_rows: int = 2000


@dataclass(frozen=True)
class Settings:
    seed: int = 42
    paths: Paths = field(default_factory=Paths)
    sizes: Sizes = field(default_factory=Sizes)
    statement_end_month: str = "2026-09"  # last full month of bank statements
    regions: tuple[str, ...] = ("North", "South", "East", "West")

    @property
    def database_url(self) -> str:
        return os.environ.get("DATABASE_URL", f"sqlite:///{REPO_ROOT / 'creditlens.db'}")


settings = Settings()
