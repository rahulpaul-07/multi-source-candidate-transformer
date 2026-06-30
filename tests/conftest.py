import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import pytest

SAMPLES = ROOT / "samples"


@pytest.fixture
def sample_inputs():
    """All sample sources, referenced by absolute path (cwd-independent).

    GitHub fixtures are passed as *.github.json files so detection routes them
    to the GitHub extractor without depending on a cache directory.
    """
    return [
        str(SAMPLES / "recruiter_export.csv"),
        str(SAMPLES / "ats_export.json"),
        str(SAMPLES / "notes" / "robert.txt"),
        str(SAMPLES / "notes" / "priya.txt"),
        str(SAMPLES / "github_cache" / "robsmith.github.json"),
        str(SAMPLES / "github_cache" / "priya-dev.github.json"),
        str(SAMPLES / "broken.json"),          # malformed on purpose
    ]
