"""typofix: ranked spelling-correction candidates from frequency dictionaries."""

from .cost import edit_cost, substitution_cost
from .engine import DEFAULT_MAX_COST, DEFAULT_TOP, Engine, load_entries

__all__ = [
    "Engine",
    "load_entries",
    "edit_cost",
    "substitution_cost",
    "DEFAULT_MAX_COST",
    "DEFAULT_TOP",
]
