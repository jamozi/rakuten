# Offline/local gates for ST-1704 publication operator v2.
override SHELL := /usr/bin/busybox
override .SHELLFLAGS := sh -eu -o pipefail -c
override SLICE_MAKEFILE := $(lastword $(MAKEFILE_LIST))
override REPOSITORY_ROOT := $(abspath $(dir $(SLICE_MAKEFILE))/../../..)
override GIT_COMMON_DIRECTORY := $(strip $(shell cd "$(REPOSITORY_ROOT)" && /usr/bin/git rev-parse --path-format=absolute --git-common-dir))
override MANAGED_PYTHON := $(abspath $(GIT_COMMON_DIRECTORY)/../.venv/bin/python)
override CLEAN_PYTHON := /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC $(MANAGED_PYTHON) -B -I -S -X pycache_prefix=/dev/null

.PHONY: help check bindings-generate manifest-generate manifest-check \
	plugin-source-check plugin-check plugin-package tests

help:
	@echo 'Offline: check manifest-check plugin-source-check plugin-check tests'
	@echo 'Generated: bindings-generate manifest-generate; private: plugin-package'
	@echo 'No target installs, activates, changes gates, calls WordPress, approves, or publishes'

check: manifest-check plugin-check tests

bindings-generate:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) scripts/build_st1704_wordpress_publication_operator_v2.py --bindings

manifest-generate:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) scripts/build_st1704_wordpress_publication_operator_v2.py --manifest

manifest-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) scripts/build_st1704_wordpress_publication_operator_v2.py --check

plugin-source-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) scripts/build_st1704_wordpress_publication_operator_v2.py --source-check

plugin-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) scripts/build_st1704_wordpress_publication_operator_v2.py --package-check

plugin-package:
	cd "$(REPOSITORY_ROOT)" && umask 0077 && $(CLEAN_PYTHON) scripts/build_st1704_wordpress_publication_operator_v2.py --package

tests:
	cd "$(REPOSITORY_ROOT)" && TMPDIR=/tmp TEMP=/tmp TMP=/tmp PYTHONDONTWRITEBYTECODE=1 "$(MANAGED_PYTHON)" -m pytest -p no:cacheprovider -q -s tests/st1704_publication_operator
