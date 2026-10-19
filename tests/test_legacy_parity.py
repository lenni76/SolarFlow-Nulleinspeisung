"""Independent golden results produced from the preserved public 1.0.0 source."""

import json
from dataclasses import asdict
from datetime import time
from pathlib import Path

from custom_components.solarflow_zero_export.legacy_calculation import calculate
from tests.test_calculation import P


def test_all_frozen_original_results_match_legacy_arithmetic():
    vectors = json.loads(Path(__file__).with_name("legacy_vectors.json").read_text())
    assert len(vectors["cases"]) == 720
    for case in vectors["cases"]:
        inputs = {**case["input"], "now": time.fromisoformat(case["input"]["now"]), "params": P}
        assert asdict(calculate(**inputs)) == case["result"]
