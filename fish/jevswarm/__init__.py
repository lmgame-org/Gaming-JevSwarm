"""Jev-driven fish schooling under predator attack."""
import os as _os
import sys as _sys

# Make the repo's shared package (common/swarmcore) importable without installing anything.
_COMMON = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))), "common")
if _COMMON not in _sys.path:
    _sys.path.insert(0, _COMMON)
