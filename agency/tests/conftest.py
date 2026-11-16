import os
import shutil
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from agency import config  # noqa: E402


@pytest.fixture
def cfg():
    return config.load(os.path.join(ROOT, "config", "agency.json"))


@pytest.fixture
def project(tmp_path):
    """A throwaway copy of the sample project (config + departments + handoffs) that tests may write to."""
    p = tmp_path / "proj"
    shutil.copytree(os.path.join(ROOT, "config"), p / "config")
    shutil.copytree(os.path.join(ROOT, "departments"), p / "departments")
    shutil.copytree(os.path.join(ROOT, "handoffs"), p / "handoffs")
    return str(p)
