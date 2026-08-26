PYTHON ?= .venv/bin/python
UV ?= uv
NPM ?= npm
DOCKER ?= docker
BASE ?=
BASE_ARGUMENT := $(if $(strip $(BASE)),--base $(BASE),)

.PHONY: setup generate check fast final final-lock final-static final-secrets \
	status-v2 test-parallel test-serial contracts database storage

setup:
	$(UV) sync --locked --group dev
	$(NPM) ci --cache .npm-cache --ignore-scripts --no-audit --no-fund
	$(PYTHON) scripts/verify_dev_toolchain.py

generate:
	$(PYTHON) scripts/raos_build.py $(BASE_ARGUMENT) generate
	$(PYTHON) scripts/status_v2.py

check: final-static
	$(PYTHON) scripts/raos_build.py $(BASE_ARGUMENT) check
	$(PYTHON) scripts/status_v2.py --check

fast:
	TMPDIR=/tmp $(PYTHON) scripts/raos_build.py $(BASE_ARGUMENT) fast

final-lock:
	$(PYTHON) scripts/verify_dev_toolchain.py
	$(UV) lock --check
	$(NPM) ls --all

final-static:
	$(PYTHON) -m ruff check python scripts tests
	$(PYTHON) -m mypy python/raos
	$(NPM) run format:check
	$(NPM) run lint
	$(NPM) run typecheck
	$(NPM) run pyright

final-secrets:
	$(PYTHON) -I scripts/scan_secrets.py --worktree \
		--reviewed-findings changes/st-0106/contracts/reviewed-secret-findings.v3.yaml

status-v2:
	$(PYTHON) scripts/status_v2.py --check

test-parallel:
	PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp $(PYTHON) -m pytest -s -p xdist.plugin -n auto \
		-m 'not serial and not live and not external and not raos_owner_private' tests

test-serial:
	PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp $(PYTHON) -m pytest -s -p xdist.plugin \
		-m 'serial and not database and not storage and not live and not external and not raos_owner_private' tests \
		|| test $$? -eq 5

contracts:
	$(PYTHON) scripts/build_st0104_contract_repository.py --check
	$(PYTHON) scripts/verify_contract_repository.py
	PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp $(PYTHON) -m pytest -q tests/st0104

database:
	scripts/postgres_service.sh --docker "$(DOCKER)" test

storage:
	scripts/object_storage_service.sh --docker "$(DOCKER)" test

final: final-lock final-static final-secrets status-v2
	TMPDIR=/tmp $(PYTHON) scripts/raos_build.py final
	$(MAKE) contracts database storage
