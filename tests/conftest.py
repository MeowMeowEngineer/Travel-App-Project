"""Every test starts with the sample fixture's city active (data/sample/site.json: a Gunsan-shaped test city), so a
helper called outside a build reads the same city the sample builds read. A build or a tool inside a test activates
the site.json of the data it loads (pipeline/city.py), and the next test starts from the sample again."""
from pathlib import Path

import pytest

from pipeline import city

SAMPLE = Path(__file__).resolve().parent.parent / "data" / "sample"


@pytest.fixture(autouse=True)
def _sample_city():
    city.activate_dir(SAMPLE)
    yield
    city.activate_dir(SAMPLE)
