"""Helpers shared by every generator. All randomness flows from one seed."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import yaml
from faker import Faker

ALIASES_FILE = Path(__file__).resolve().parents[1] / "pipeline" / "aliases.yaml"


def rng_for(seed: int, stream: str) -> np.random.Generator:
    """Independent, reproducible random stream per generator."""
    offset = sum(ord(c) * (i + 1) for i, c in enumerate(stream))
    return np.random.default_rng(seed * 1_000_003 + offset)


def faker_for(seed: int, stream: str) -> Faker:
    fake = Faker("en_IN")
    fake.seed_instance(seed * 7919 + sum(ord(c) for c in stream))
    return fake


def format_inr(value: float, decimals: int = 2) -> str:
    """Format with Indian digit grouping: 1234567.5 -> '12,34,567.50'."""
    negative = value < 0
    value = abs(value)
    whole, frac = f"{value:.{decimals}f}".split(".") if decimals else (f"{value:.0f}", "")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        groups = []
        while len(head) > 2:
            groups.insert(0, head[-2:])
            head = head[:-2]
        if head:
            groups.insert(0, head)
        whole = ",".join(groups + [tail])
    text = f"{whole}.{frac}" if decimals else whole
    return f"-{text}" if negative else text


def load_aliases() -> dict[str, str]:
    """Abbreviation map shared with the pipeline (abbreviation -> canonical word)."""
    return yaml.safe_load(ALIASES_FILE.read_text())["abbreviations"]


def counterparty_variant(canonical: str, rng: np.random.Generator, aliases: dict[str, str]) -> str:
    """Render one messy spelling of a canonical counterparty name."""
    reverse = {}
    for abbr, word in aliases.items():
        reverse.setdefault(word, abbr)
    choice = rng.integers(0, 6)
    words = canonical.split()
    if choice == 0:
        return canonical
    if choice == 1:
        return canonical.title()
    if choice == 2:
        return f"{canonical} PVT LTD"
    if choice == 3:
        return f"{canonical.title()} Private Limited"
    if choice == 4:
        swapped = [reverse.get(w, w) for w in words]
        return " ".join(swapped)
    return "  ".join(words).lower() + "."


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str))
