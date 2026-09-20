"""next30 Wave 1 round 5 (2026-09-20): the theme suite writes only under its own root.

A gate that cannot tell a pre-existing failure from a new one is not a gate. On
this branch the eight-path pytest set reported two failures on some runs and
three on others: ``tests/st1704/test_self_hosted_editorial_release_contract.py::
test_repository_make_theme_checks_load_only_locked_build_dependencies`` failed
with ``SELF_HOSTED_EDITORIAL_THEME_INVALID`` in three of seven runs of the same
committed tree, and in none of five runs of the same command on ``origin/main``.

The mechanism is a write that escapes a temporary root.
``test_theme_stamp_generator_converges_once_is_idempotent_and_rotates`` copies
the theme into ``tmp_path`` and rebinds ``build_st1704_self_hosted_theme
.THEME_ROOT`` to the copy, but ``render_theme_stamp_payloads`` keys the reader
runtime asset by ``ROOT / READER_RUNTIME_ASSET_PATH`` -- an absolute path into
the tracked theme -- while every other payload is keyed by ``THEME_ROOT``. So
the copy test wrote ``assets/reader-measurement-runtime.v1.json`` back into the
repository three times per run, each time through a
``.reader-measurement-runtime.v1.json.<pid>.<n>.tmp`` staged beside it. The
bytes were identical, so ``git status`` stayed empty and nothing looked wrong;
but while that staged file existed, ``--check``'s ``_validate_exact_tree`` saw a
path that is not in ``SOURCE_FILES`` and exited 1. Whichever test happened to be
running ``make theme-check`` at that instant failed.

This file states the invariant the gate needs: running that test leaves the
tracked theme byte-identical *and* file-identical -- the inode is the check that
matters, because ``os.replace`` of an identical payload is invisible to content
comparison and to ``git status`` but is exactly what the race needs. No ``\\b``
is used next to Japanese text.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

import pytest

from scripts import build_st1704_self_hosted_theme as theme_builder

ROOT = Path(__file__).resolve().parents[2]
THEME = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child"
)
READER_RUNTIME_ASSET = THEME / "assets/reader-measurement-runtime.v1.json"
WRITING_TEST = (
    "tests/st1704/test_self_hosted_editorial_theme.py"
    "::test_theme_stamp_generator_converges_once_is_idempotent_and_rotates"
)


def _identity(path: Path) -> tuple[int, int, bytes]:
    """Inode, mtime and bytes: a rewrite changes the first two, not the third."""

    status = path.stat()
    return (status.st_ino, status.st_mtime_ns, path.read_bytes())


def _run(selection: str) -> subprocess.CompletedProcess[str]:
    environment = dict(os.environ)
    environment["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", selection],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
        env=environment,
    )


@pytest.fixture(scope="module")
def theme_stamp_test_run() -> tuple[tuple[int, int, bytes], tuple[int, int, bytes]]:
    """Run the copy test once and hand both checks what the tracked tree did."""

    before = _identity(READER_RUNTIME_ASSET)
    result = _run(WRITING_TEST)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-2000:]
    return before, _identity(READER_RUNTIME_ASSET)


def test_the_theme_stamp_test_writes_nothing_into_the_tracked_theme(
    theme_stamp_test_run: tuple[tuple[int, int, bytes], tuple[int, int, bytes]],
) -> None:
    before, after = theme_stamp_test_run
    assert after[0] == before[0], (
        "the theme stamp test replaced the tracked reader runtime asset "
        f"(inode {before[0]} -> {after[0]}); it must write under its own root"
    )
    assert after == before


def test_the_tracked_theme_still_holds_exactly_the_builder_source_files(
    theme_stamp_test_run: tuple[tuple[int, int, bytes], tuple[int, int, bytes]],
) -> None:
    """``--check`` fails on any path the builder does not name, staged ones too."""

    observed = tuple(
        sorted(
            path.relative_to(THEME).as_posix()
            for path in THEME.rglob("*")
            if path.is_file()
        )
    )
    assert observed == theme_builder.SOURCE_FILES, sorted(
        set(observed).symmetric_difference(theme_builder.SOURCE_FILES)
    )
