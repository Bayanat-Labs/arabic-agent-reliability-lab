from pathlib import Path

import pytest

from bayanat_lab.settings import DEFAULT_SUITE
from bayanat_lab.suites import load_suite


@pytest.fixture(scope="session")
def suite_path() -> Path:
    return DEFAULT_SUITE


@pytest.fixture(scope="session")
def suite(suite_path):
    return load_suite(suite_path)
