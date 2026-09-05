"""Expose test outcomes, including environment skips, in the Actions summary."""

import os

from _pytest.terminal import TerminalReporter


def pytest_terminal_summary(terminalreporter: TerminalReporter) -> None:
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary:
        return
    counts = ", ".join(
        f"{outcome}={len(terminalreporter.stats.get(outcome, ()))}"
        for outcome in ("passed", "failed", "error", "skipped", "deselected")
    )
    label = os.environ.get("RAOS_CHECK_LABEL", "pytest")
    with open(summary, "a", encoding="utf-8") as stream:
        stream.write(f"- {label} outcomes: {counts}. Skipped cases were not executed.\n")
