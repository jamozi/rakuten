override SHELL := /usr/bin/busybox
override .SHELLFLAGS := sh -eu -o pipefail -c
override SLICE_MAKEFILE := $(lastword $(MAKEFILE_LIST))
override REPOSITORY_ROOT := $(abspath $(dir $(SLICE_MAKEFILE))/../..)
override GIT_COMMON_DIRECTORY := $(strip $(shell cd "$(REPOSITORY_ROOT)" && /usr/bin/git rev-parse --path-format=absolute --git-common-dir))
override MANAGED_PYTHON := $(abspath $(GIT_COMMON_DIRECTORY)/../.venv/bin/python)
override CLEAN_PYTHON := /usr/bin/env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC $(MANAGED_PYTHON) -B -I -S -X pycache_prefix=/dev/null

.PHONY: check generate package tests

generate:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) scripts/build_editorial_measurement_v1.py --generate

check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) scripts/build_editorial_measurement_v1.py --check
	$(MAKE) tests

package:
	cd "$(REPOSITORY_ROOT)" && umask 0077 && $(CLEAN_PYTHON) scripts/build_editorial_measurement_v1.py --package

tests:
	cd "$(REPOSITORY_ROOT)" && PYTHONDONTWRITEBYTECODE=1 "$(MANAGED_PYTHON)" -m pytest -p no:cacheprovider -q tests/editorial_measurement_v1
