"""Keeps .env.example honest: a value copied from it must not silently undo a default in app/config.py."""

from app.config import Settings
from tests.conftest import ROOT


def _example_values() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            name, value = line.split("=", 1)
            values[name.strip().lower()] = value.strip()
    return values


def test_every_example_setting_exists():
    unknown = set(_example_values()) - set(Settings.model_fields)
    assert not unknown, f".env.example names settings that app/config.py does not have: {unknown}"


def test_example_values_match_the_code_defaults():
    # Read the declared defaults, not a Settings() instance, so the machine's environment cannot leak in.
    for name, raw in _example_values().items():
        default = Settings.model_fields[name].default
        if isinstance(default, bool):
            matches = raw.lower() == str(default).lower()
        elif isinstance(default, int | float):
            matches = float(raw) == float(default)
        else:
            matches = raw == default
        assert matches, f"{name} in .env.example differs from the default in app/config.py"


def test_example_file_contains_no_secrets():
    for name, raw in _example_values().items():
        if "key" in name:
            assert raw == "", f"{name} must be left empty in .env.example"
