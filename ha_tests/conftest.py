"""Real HA fixtures; load the unchanged API reference from a separate checkout."""

import os
import sys
from pathlib import Path

import pytest

API_ROOT = Path(
    os.environ.get(
        "SOLARFLOW_TEST_API_ROOT", str(Path(__file__).parents[2] / "SolarFlow2400ProAPI")
    )
)
sys.path.insert(0, str(API_ROOT))

# Import before HA's fixtures establish their test namespace, as in the API tests.
from custom_components.solarflow2400_api.const import DOMAIN as API_DOMAIN  # noqa: E402,F401

from custom_components.solarflow_zero_export.const import DOMAIN as DOMAIN  # noqa: E402,F401


@pytest.fixture(autouse=True)
def enable_local_integrations(enable_custom_integrations):
    """Allow both actual integrations in the isolated HA instance."""


from ha_tests.test_coupling import pair as pair  # noqa: E402
