override SHELL := /usr/bin/busybox
override .SHELLFLAGS := sh -eu -o pipefail -c
override SLICE_MAKEFILE := $(lastword $(MAKEFILE_LIST))
override REPOSITORY_ROOT := $(abspath $(dir $(SLICE_MAKEFILE))/../..)
override GIT_COMMON_DIRECTORY := $(strip $(shell cd "$(REPOSITORY_ROOT)" && /usr/bin/git rev-parse --path-format=absolute --git-common-dir))
override MANAGED_PYTHON := $(abspath $(GIT_COMMON_DIRECTORY)/../.venv/bin/python)
override CLEAN_PYTHON := /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC $(MANAGED_PYTHON) -B -I -S -X pycache_prefix=/dev/null

.PHONY: help check e2e manifest-generate manifest-check source-check plugin-package plugin-package-check tests

help:
	@echo 'Offline: check manifest-check source-check tests'
	@echo 'Disposable external: e2e (requires Docker and downloads the digest-pinned MCP Adapter asset)'
	@echo 'Generated: manifest-generate; owner-private: plugin-package plugin-package-check'
	@echo 'No target installs, activates, configures credentials, approves, calls WordPress, or applies changes'

check: manifest-check source-check tests

manifest-generate:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) scripts/build_wordpress_mcp_v1.py --manifest

manifest-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) scripts/build_wordpress_mcp_v1.py --check

source-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) scripts/build_wordpress_mcp_v1.py --source-check

plugin-package:
	cd "$(REPOSITORY_ROOT)" && umask 0077 && $(CLEAN_PYTHON) scripts/build_wordpress_mcp_v1.py --package

plugin-package-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) scripts/build_wordpress_mcp_v1.py --package-check

tests:
	cd "$(REPOSITORY_ROOT)" && TMPDIR=/tmp TEMP=/tmp TMP=/tmp PYTHONDONTWRITEBYTECODE=1 "$(MANAGED_PYTHON)" -m pytest -p no:cacheprovider -q -s tests/wordpress_mcp_v1

e2e:
	cd "$(REPOSITORY_ROOT)" && /usr/bin/bash tests/wordpress_mcp_v1/e2e/run.sh
