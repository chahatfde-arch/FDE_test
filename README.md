<<<<<<< HEAD
# CreditLens AI

CreditLens AI turns a small-business loan application into a draft credit memo for Kestrel Finance, a fictional lender. A human underwriter makes every final decision. All data is synthetic and every tool used is free.

## Status

| Milestone | What it delivers | Status |
| --- | --- | --- |
| 1. Synthetic data generators | Registry, applications, messy bank statements, financial statement PDFs (some scanned), policy manual, loan history, answer key | Done |
| 2. Data pipeline | Raw to clean to curated layers, Pandera contracts, async ingestion lab, database load | Done |
| 3. API and tracing | FastAPI service, Langfuse | Next |
| 4 to 11 | Extraction, retrieval, agents, MLOps, security, deploy, Evaluate and Maintain, workshop packaging | Planned |

## Quickstart

### Google Colab

Open `notebooks/01_data_foundation.ipynb` in Colab, set your repo URL in the first cell, and run all cells.

### VS Code (laptop)

```bash
git clone https://github.com/YOUR-USERNAME/creditlens-ai.git
cd creditlens-ai
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
```

PDF rendering needs Poppler: `sudo apt install poppler-utils` on Linux or WSL, `brew install poppler` on macOS.

```bash
python -m creditlens.generators          # milestone 1: generate all data (a few seconds)
python -m creditlens.pipeline --load     # milestone 2: clean, curate and load the database
python -m creditlens.pipeline.ingest     # Day 1 lab: sequential vs asyncio vs threads vs processes
pytest -q                                # prove everything
```

### SQL Server instead of SQLite

The default database is a local SQLite file, so everything works in Colab. To use SQL Server Developer edition (free for development):

```bash
docker compose -f infra/docker-compose.yml up -d
pip install -e ".[mssql]"
```

Install Microsoft's ODBC Driver 18 for SQL Server, then set `DATABASE_URL` in `.env` to the SQL Server line from `.env.example` and rerun `python -m creditlens.pipeline --load`.

## What the generators create

| Path | Contents |
| --- | --- |
| `data/raw/registry/` | 40 companies, their directors (with synthetic PII), director links, users for RBAC, existing loans |
| `data/raw/applications/` | 30 loan applications |
| `data/raw/statements/` | 12 months of transactions per application, in two bank layouts with planted problems; 6 also as PDF |
| `data/raw/financials/` | 3 years of financial statements per applicant as PDFs, a quarter of them scanned, one with page 2 rotated |
| `data/raw/policy/` | The fictional credit policy manual (Markdown and PDF) |
| `data/raw/history/` | 2,000 historical loans with outcomes, for the risk model |
| `data/answer_key/` | Instructor-only truth: clean transactions, planted issues, financial values, related-party groups, expected policy flags |

Never give `data/answer_key/` to workshop pods. Every count above comes from the defaults in `src/creditlens/config.py`.

### Planted problems in bank statements

Mixed date formats, amounts stored as text with currency symbols, exact duplicate rows, counterparty spelling variants, missing balances, missing descriptions, and messy headers. Each file gets a few of them, and every problem appears in several files.

## How the pipeline fixes them

| Problem | Fix | Code |
| --- | --- | --- |
| Two bank layouts, messy headers | Normalize headers, detect layout | `wrangle.normalize_header`, `detect_layout` |
| Exact duplicate rows | Drop repeats of the full raw row | `clean.clean_statement` |
| Mixed date formats | Try known formats in order, accept only dates inside the statement window | `wrangle.parse_date` |
| Currency text in amounts | Strip symbols and Indian digit grouping, handle brackets as negatives | `wrangle.parse_amount` |
| Counterparty variants | Upper-case, strip legal suffixes, expand abbreviations from `aliases.yaml` | `wrangle.normalize_counterparty` |
| Missing balances | Rebuild from the running total | `clean.clean_statement` |
| Missing descriptions | Mark as `UNKNOWN` and report the share per application | `wrangle.parse_narration`, `features.build_features` |

The clean layer must pass `contracts.clean_transactions`, which checks types, channels, upper-case names, unique sequence numbers, and that every balance follows from the previous one. The curated layer must pass `contracts.statement_features`.

`tests/test_pipeline.py` proves milestone 2 is done: the cleaned transactions match the generator's truth exactly, the quality report matches every planted problem, and banking-conduct rules 4.1 and 4.2 agree with the answer key.

## Repo layout

```
src/creditlens/
  config.py           seed, sizes, paths, DATABASE_URL
  generators/         milestone 1
  pipeline/           milestone 2
tests/                pytest suite
notebooks/            Colab notebooks, one per milestone
infra/                docker-compose.yml
.github/workflows/    CI runs the tests on every push
```
=======
# FDE_test
>>>>>>> 25e17e14aa65d7629e7c91540cb3ef1e3d33b666
