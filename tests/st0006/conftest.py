"""Pytest entrypoint; reusable helpers live in support.py."""

from . import support as _support


for _name in dir(_support):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_support, _name)
del _name, _support
