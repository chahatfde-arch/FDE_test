"""Load clean and curated tables into the database (SQLite by default, SQL Server via DATABASE_URL)."""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from sqlalchemy import create_engine, inspect

REGISTRY_TABLES = ["companies", "directors", "company_directors", "users", "existing_loans"]


def get_engine(url: str):
    kwargs = {"fast_executemany": True} if url.startswith("mssql") else {}
    return create_engine(url, **kwargs)


def load_all(url: str, raw_dir: Path, tables: dict[str, pd.DataFrame]) -> list[str]:
    """Write registry, applications and pipeline outputs. Tables are replaced on each run."""
    engine = get_engine(url)
    frames = {name: pd.read_csv(raw_dir / "registry" / f"{name}.csv") for name in REGISTRY_TABLES}
    frames["applications"] = pd.read_csv(raw_dir / "applications" / "applications.csv")
    frames.update(tables)
    with engine.begin() as conn:
        for name, df in frames.items():
            df.to_sql(name, conn, if_exists="replace", index=False, chunksize=1000)
    return sorted(inspect(engine).get_table_names())
