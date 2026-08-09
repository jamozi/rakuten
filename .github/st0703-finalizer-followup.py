from __future__ import annotations

from pathlib import Path

path = Path(".github/st0703-finalize.sh")
text = path.read_text(encoding="utf-8")

manifest_anchor = (
    ".venv/bin/python scripts/build_local_compose.py\n"
    ".venv/bin/python scripts/build_local_compose.py --check\n\n"
    "scripts/run_network_denied.sh --home \"$HOME\" -- \\\n"
)
manifest_replacement = (
    ".venv/bin/python scripts/build_local_compose.py\n"
    ".venv/bin/python scripts/build_local_compose.py --check\n"
    ".venv/bin/python scripts/build_st0801_content_ast.py\n"
    ".venv/bin/python scripts/build_st0801_content_ast.py --check\n\n"
    "scripts/run_network_denied.sh --home \"$HOME\" -- \\\n"
)
if text.count(manifest_anchor) != 1:
    raise SystemExit("unexpected post-workflow manifest regeneration anchor")
text = text.replace(manifest_anchor, manifest_replacement, 1)

combined = (
    ".venv/bin/python -m pytest -p no:cacheprovider -q \\\n"
    "  tests/st0204 tests/st0701 tests/st0703 tests/st0801\n"
)
isolated = (
    "for suite in st0204 st0701 st0703 st0801; do\n"
    "  .venv/bin/python -m pytest -p no:cacheprovider -q \"tests/$suite\"\n"
    "done\n"
)
if text.count(combined) != 1:
    raise SystemExit("unexpected combined Story suite command")
text = text.replace(combined, isolated, 1)

cleanup_anchor = "  .github/st0703-finalize.sh\n"
cleanup_replacement = (
    "  .github/st0703-finalize.sh \\\n"
    "  .github/st0703-finalizer-followup.py\n"
)
if text.count(cleanup_anchor) != 1:
    raise SystemExit("unexpected finalizer cleanup anchor")
text = text.replace(cleanup_anchor, cleanup_replacement, 1)

path.write_text(text, encoding="utf-8", newline="")
