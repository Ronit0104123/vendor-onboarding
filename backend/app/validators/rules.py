"""Loads country and state rules from /config so adding a country is a YAML edit."""
import re
from functools import lru_cache

import yaml

from app.config import BACKEND_DIR


@lru_cache
def countries() -> dict:
    with open(BACKEND_DIR / "config" / "countries.yaml") as f:
        return yaml.safe_load(f)


@lru_cache
def state_codes() -> dict[str, str]:
    """Lower-cased state name -> 2-digit GST state code."""
    with open(BACKEND_DIR / "config" / "states.yaml") as f:
        return {name.lower(): code for name, code in yaml.safe_load(f).items()}


def matches(pattern: str, value: str) -> bool:
    return re.fullmatch(pattern, value or "") is not None
