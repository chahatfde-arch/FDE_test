import pandas as pd

from creditlens.pipeline import ingest
from creditlens.pipeline.run import statement_window


def test_all_strategies_give_identical_results(s, monkeypatch):
    monkeypatch.setattr(ingest, "API_LATENCY_S", 0.01)
    paths = sorted((s.paths.raw / "statements").glob("*.csv"))[:6]
    window = statement_window(s)
    base = pd.concat(ingest.run_sequential(paths, window), ignore_index=True)
    for name in ("asyncio", "threads"):
        pd.testing.assert_frame_equal(base, pd.concat(ingest.STRATEGIES[name](paths, window), ignore_index=True))
