#!/bin/bash -p
set -euo pipefail

PATH=/usr/bin:/bin:${PATH:-}
export PATH
export PYTHONDONTWRITEBYTECODE=1

: "${HEAD_REF:?HEAD_REF is required}"
: "${HEAD_SHA:?HEAD_SHA is required}"
readonly expected_compatibility_payload_blob='6e7f9b678eac136539a212d63481e9b0907b718e'
readonly expected_compatibility_patch_sha='b5d46c704b2b88b4e275748d08502c5119e2847f5e2da79bba1528880480c5b7'
readonly expected_netns_payload_sha='fdd1eca834ededd1801b3bad908af75b868872b1584c038619f4b8d08742a7a0'
readonly expected_netns_patch_sha='ab4eba2e75c479b8d0e6db4a1dfb75bfd3d374ed7157a3d4c3f9a394a6dd2166'

test "$(git rev-parse HEAD)" = "$HEAD_SHA"
cp -- .github/workflows/ci.yml "$RUNNER_TEMP/st0703-transport-ci.yml"

compatibility_payload=.github/infra-compatibility.patch.gz.b64
compatibility_patch="$RUNNER_TEMP/infra-compatibility.patch"
test "$(git hash-object "$compatibility_payload")" = \
  "$expected_compatibility_payload_blob"
base64 --decode "$compatibility_payload" | gzip --decompress \
  > "$compatibility_patch"
test "$(sha256sum "$compatibility_patch" | cut -d' ' -f1)" = \
  "$expected_compatibility_patch_sha"
git apply --check "$compatibility_patch"
git apply "$compatibility_patch"

netns_payload="$RUNNER_TEMP/st0202-internal-netns.patch.gz.b64"
netns_patch="$RUNNER_TEMP/st0202-internal-netns.patch"
cat \
  .github/st0202-internal-netns.patch.gz.b64.part00 \
  .github/st0202-internal-netns.patch.gz.b64.part01 \
  .github/st0202-internal-netns.patch.gz.b64.part02 \
  .github/st0202-internal-netns.patch.gz.b64.part03 \
  > "$netns_payload"
test "$(sha256sum "$netns_payload" | cut -d' ' -f1)" = \
  "$expected_netns_payload_sha"
base64 --decode "$netns_payload" | gzip --decompress > "$netns_patch"
test "$(sha256sum "$netns_patch" | cut -d' ' -f1)" = \
  "$expected_netns_patch_sha"
patch --dry-run --batch --forward -p1 < "$netns_patch"
patch --batch --forward -p1 < "$netns_patch"
git diff --check
bash -n scripts/run_network_denied.sh
bash -n scripts/object_storage_service.sh

uv_path=$(command -v uv)
env -i PATH=/usr/bin:/bin HOME="$HOME" LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
  "$uv_path" --no-config --color never python install \
  --managed-python --no-bin --no-registry --no-cache --no-progress 3.14.6
env -i PATH=/usr/bin:/bin HOME="$HOME" LANG=C.UTF-8 LC_ALL=C.UTF-8 TZ=UTC \
  "$uv_path" --no-config --color never sync --locked \
  --no-default-groups --group dev --no-install-project --no-install-local \
  --managed-python --no-python-downloads --python 3.14.6 \
  --no-build --no-sources --default-index https://pypi.org/simple \
  --index-strategy first-index --keyring-provider disabled --link-mode copy \
  --resolution highest --prerelease disallow \
  --exclude-newer 2026-08-01T16:50:16Z --no-cache --no-progress

.venv/bin/python scripts/build_local_compose.py
compose_sha=$(sha256sum docker-compose.yml | cut -d' ' -f1)
.venv/bin/python - "$compose_sha" <<'PY'
from pathlib import Path
import re
import sys

for relative in (
    "scripts/postgres_service.sh",
    "scripts/object_storage_service.sh",
):
    path = Path(relative)
    text = path.read_text(encoding="utf-8")
    text, count = re.subn(
        r"readonly expected_compose_sha256='[0-9a-f]{64}'",
        f"readonly expected_compose_sha256='{sys.argv[1]}'",
        text,
        count=1,
    )
    if count != 1:
        raise SystemExit(f"unexpected Compose digest binding source: {relative}")
    path.write_text(text, encoding="utf-8", newline="")
PY
.venv/bin/python scripts/build_local_compose.py
.venv/bin/python scripts/build_local_compose.py --check
.venv/bin/python scripts/build_st0703_recorded_adapter.py
.venv/bin/python scripts/build_st0703_recorded_adapter.py --check

.venv/bin/python -m ruff format \
  scripts/build_local_compose.py \
  tests/st0106/test_network_isolation.py \
  tests/st0106/test_hydration_validator.py \
  tests/st0201/test_wrapper.py \
  tests/st0202 \
  tests/st0703
.venv/bin/python scripts/build_local_compose.py
.venv/bin/python scripts/build_local_compose.py --check
.venv/bin/python scripts/build_st0703_recorded_adapter.py --check
.venv/bin/python -m ruff check \
  python/raos scripts/build_local_compose.py \
  scripts/build_st0703_recorded_adapter.py \
  tests/st0106 tests/st0201 tests/st0202 tests/st0703
.venv/bin/python -m ruff format --check \
  --exclude python/raos/generated \
  python/raos scripts/build_local_compose.py \
  scripts/build_st0703_recorded_adapter.py \
  tests/st0106 tests/st0201 tests/st0202 tests/st0703
.venv/bin/python -m mypy

# The ST-0106 workflow contract must inspect the canonical pull-request CI,
# while every generated-manifest test must see the branch's unchanged transport CI.
git show origin/main:.github/workflows/ci.yml > .github/workflows/ci.yml
.venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/st0106/test_workflow_contract.py
cp -- "$RUNNER_TEMP/st0703-transport-ci.yml" .github/workflows/ci.yml

scripts/run_network_denied.sh --home "$HOME" -- \
  "$GITHUB_WORKSPACE/.venv/bin/pytest" \
  -p no:cacheprovider -q tests/st0106 \
  --ignore=tests/st0106/test_workflow_contract.py
scripts/run_network_denied.sh --home "$HOME" -- \
  "$GITHUB_WORKSPACE/.venv/bin/pytest" \
  -p no:cacheprovider -q tests/st0201
scripts/run_network_denied.sh --home "$HOME" -- \
  "$GITHUB_WORKSPACE/.venv/bin/pytest" \
  -p no:cacheprovider -q tests/st0202
.venv/bin/python -m pytest -p no:cacheprovider -q \
  tests/st0204 tests/st0701 tests/st0703 tests/st0801

scripts/object_storage_service.sh --docker "$(command -v docker)" test

cat > changes/st-0202/IMPLEMENTATION_VALIDATION.md <<EVIDENCE
# ST-0202 implementation-candidate validation

GitHub Actions run: ${GITHUB_RUN_ID}
Source head: ${HEAD_SHA}

The disposable SeaweedFS service remained on an internal-only bridge with no
host port. The authenticated fixture entered only the service network namespace,
dropped to the original non-root identity with all capabilities removed, and
completed the maintained S3 acceptance flow.

This is implementation-candidate evidence only. Formal TST-014, canonical Story
status, staging, production, retention-policy approval, and vulnerability-scan
approval remain unchanged or NOT_EXECUTED.
EVIDENCE

rm -f -- \
  .github/infra-compatibility-repair.py \
  .github/infra-compatibility.patch.gz.b64 \
  .github/st0703-ci-trigger \
  .github/st0703-runtime-port-fix.py \
  .github/st0703-port-diagnostic.py \
  .github/st0202-internal-netns.patch.gz.b64.part00 \
  .github/st0202-internal-netns.patch.gz.b64.part01 \
  .github/st0202-internal-netns.patch.gz.b64.part02 \
  .github/st0202-internal-netns.patch.gz.b64.part03 \
  .github/st0703-finalize.sh

git diff --check
git config user.name 'github-actions[bot]'
git config user.email '41898282+github-actions[bot]@users.noreply.github.com'
git add -A
git diff --cached --check
if git diff --cached --quiet; then
  printf 'error: materialization produced no commit\n' >&2
  exit 1
fi
git commit -m 'Finalize ST-0703 and internal object-storage runtime'
git push origin "HEAD:refs/heads/$HEAD_REF"
