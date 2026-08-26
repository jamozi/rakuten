#!/usr/bin/env python3
"""Normalize suite-local imports so the repository can be collected at once."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
DIRECT_IMPORT = "from conftest import"
PACKAGE_IMPORT = "from .conftest import"
SUPPORT_IMPORT = "from .support import"
CONFTEST_WRAPPER = '''"""Pytest entrypoint; reusable helpers live in support.py."""

from . import support as _support


for _name in dir(_support):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_support, _name)
del _name, _support
'''


def main() -> int:
    changed = 0
    packages: set[Path] = set()
    suite_directories = sorted(path for path in TESTS.iterdir() if path.is_dir())
    for package in suite_directories:
        modules = {
            path.stem
            for path in package.glob("*.py")
            if path.name not in {"__init__.py", "conftest.py"}
        }
        for path in sorted(package.glob("*.py")):
            source = path.read_text(encoding="utf-8")
            updated = source.replace(DIRECT_IMPORT, PACKAGE_IMPORT)
            for module in modules:
                updated = updated.replace(f"from {module} import", f"from .{module} import")
            if updated != source:
                path.write_text(updated, encoding="utf-8")
                changed += 1
                packages.add(package)
    for package in sorted(packages):
        marker = package / "__init__.py"
        if not marker.exists():
            marker.write_text(
                '"""Package marker for aggregate pytest import isolation."""\n',
                encoding="utf-8",
            )
            changed += 1
    support_packages = {
        path.parent
        for path in TESTS.rglob("*.py")
        if PACKAGE_IMPORT in path.read_text(encoding="utf-8")
    }
    for package in sorted(support_packages):
        conftest = package / "conftest.py"
        support = package / "support.py"
        if not support.exists():
            support.write_text(conftest.read_text(encoding="utf-8"), encoding="utf-8")
            conftest.write_text(CONFTEST_WRAPPER, encoding="utf-8")
            changed += 2
        for path in package.glob("*.py"):
            source = path.read_text(encoding="utf-8")
            updated = source.replace(PACKAGE_IMPORT, SUPPORT_IMPORT)
            if updated != source:
                path.write_text(updated, encoding="utf-8")
                changed += 1
        packages.add(package)
    print(f"RAOS_TEST_PACKAGES changed={changed} packages={len(packages)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
