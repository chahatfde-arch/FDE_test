"""Ingest statements from a (simulated) slow bank API four different ways.

Day 1 lab: predict which strategy is fastest, then run
    python -m creditlens.pipeline.ingest
Fetching is I/O-bound (waiting on the network), so concurrency helps.
Cleaning is CPU-bound (pandas work), so only processes give true parallelism.
"""
from __future__ import annotations

import asyncio
import time
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from datetime import date
from pathlib import Path

import pandas as pd

from creditlens.pipeline.clean import clean_statement

API_LATENCY_S = 0.15  # pretend each download takes this long


class BankApiSession:
    """Async context manager: opens a 'connection pool' and caps concurrent requests."""

    def __init__(self, max_concurrency: int = 8):
        self.max_concurrency = max_concurrency
        self.requests = 0

    async def __aenter__(self) -> "BankApiSession":
        self._sem = asyncio.Semaphore(self.max_concurrency)
        await asyncio.sleep(0.01)  # handshake
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        await asyncio.sleep(0.01)  # close connections cleanly, even after an error
        return False  # never swallow exceptions

    async def fetch(self, path: Path) -> Path:
        async with self._sem:
            await asyncio.sleep(API_LATENCY_S)
            self.requests += 1
            return path


def _fetch_blocking(path: Path) -> Path:
    time.sleep(API_LATENCY_S)
    return path


def _fetch_and_clean(path: Path, window: tuple[date, date]) -> pd.DataFrame:
    return clean_statement(_fetch_blocking(path), window)[0]


def run_sequential(paths, window):
    return [clean_statement(_fetch_blocking(p), window)[0] for p in paths]


async def _run_asyncio(paths, window):
    async with BankApiSession(max_concurrency=8) as api:
        fetched = await asyncio.gather(*(api.fetch(p) for p in paths))
        # Cleaning in a worker thread keeps the event loop free for other requests.
        return await asyncio.gather(*(asyncio.to_thread(clean_statement, p, window) for p in fetched))


def run_asyncio(paths, window):
    return [df for df, _ in asyncio.run(_run_asyncio(paths, window))]


def run_threads(paths, window, workers: int = 8):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_fetch_and_clean, paths, [window] * len(paths)))


def run_processes(paths, window, workers: int = 4):
    with ProcessPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(_fetch_and_clean, paths, [window] * len(paths)))


STRATEGIES = {"sequential": run_sequential, "asyncio": run_asyncio, "threads": run_threads,
              "processes": run_processes}


def benchmark(paths: list[Path], window) -> dict[str, float]:
    results, timings = {}, {}
    for name, fn in STRATEGIES.items():
        t0 = time.perf_counter()
        results[name] = pd.concat(fn(paths, window), ignore_index=True)
        timings[name] = round(time.perf_counter() - t0, 2)
    base = results["sequential"]
    for name, df in results.items():
        pd.testing.assert_frame_equal(base, df, check_like=False)  # same answer, every strategy
    return timings


def main() -> None:
    from creditlens.config import settings
    from creditlens.pipeline.run import statement_window

    paths = sorted((settings.paths.raw / "statements").glob("*.csv"))
    print(f"{len(paths)} statements, simulated API latency {API_LATENCY_S}s each\n")
    for name, secs in benchmark(paths, statement_window(settings)).items():
        print(f"{name:>10}: {secs:6.2f}s")


if __name__ == "__main__":
    main()
