"""Shared fixtures: generate a fresh dataset once per test session in a temp folder."""
from dataclasses import replace

import pytest

from creditlens.config import settings
from creditlens.generators.generate_all import generate_all
from creditlens.pipeline.run import run_pipeline


@pytest.fixture(scope="session")
def s(tmp_path_factory):
    root = tmp_path_factory.mktemp("data")
    cfg = replace(settings, paths=settings.paths.with_data_root(root))
    generate_all(cfg, verbose=False)
    return cfg


@pytest.fixture(scope="session")
def outputs(s):
    return run_pipeline(s, verbose=False)
