# Repository-local gates for ST-1704 SELF_HOSTED_EDITORIAL_PILOT_V1.
# Invoke from the repository root with:
#   make -f changes/st-1704/self-hosted-editorial-pilot-v1/Makefile <target>

override EDITORIAL_MAKE_SHORT_FLAGS := $(firstword $(MAKEFLAGS))
ifneq ($(filter -%,$(EDITORIAL_MAKE_SHORT_FLAGS)),)
override EDITORIAL_MAKE_SHORT_FLAGS :=
endif
override EDITORIAL_UNSAFE_MAKE_MODES := $(strip $(foreach flag,e i n t,$(if $(findstring $(flag),$(EDITORIAL_MAKE_SHORT_FLAGS)),$(flag))))

ifeq ($(origin MAKEFLAGS),command line)
$(error Direct MAKEFLAGS assignments are not allowed for repository-local gates)
endif
ifneq ($(strip $(MAKEFILES)),)
$(error Preloaded MAKEFILES are not allowed for repository-local gates)
endif
ifneq ($(EDITORIAL_UNSAFE_MAKE_MODES),)
$(error Refusing non-verifying GNU Make mode(s): $(EDITORIAL_UNSAFE_MAKE_MODES))
endif

override SHELL := /usr/bin/busybox
override .SHELLFLAGS := sh -eu -o pipefail -c
override EDITORIAL_MAKEFILE := $(lastword $(MAKEFILE_LIST))
override REPOSITORY_ROOT := $(abspath $(dir $(EDITORIAL_MAKEFILE))/../../..)
override MANAGED_PYTHON := $(REPOSITORY_ROOT)/.venv/bin/python
override CLEAN_PYTHON := /usr/bin/env -i PATH=/usr/bin:/bin \
	LANG=C LC_ALL=C TZ=UTC \
	$(MANAGED_PYTHON) -B -I -S -X pycache_prefix=/dev/null

.PHONY: help check manifest-generate manifest-check theme-source-check \
	theme-check theme-package tests cli-help source-cli-help

help:
	@echo 'Offline: check manifest-check theme-source-check theme-check tests cli-help source-cli-help'
	@echo 'Local artifacts: manifest-generate theme-package'
	@echo 'Article operations: use the four closed subcommands shown by cli-help'
	@echo 'Read-only source capture: use the two closed subcommands shown by source-cli-help'
	@echo 'Source capture process: repository-root CLEAN_PYTHON only (-B -I -S; ambient environment removed)'

check: manifest-check theme-source-check theme-check tests

manifest-generate:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1704_self_hosted_editorial_manifest.py

manifest-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1704_self_hosted_editorial_manifest.py --check

theme-source-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1704_self_hosted_theme.py --source-check

theme-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1704_self_hosted_theme.py --check

theme-package:
	cd "$(REPOSITORY_ROOT)" && umask 0077 && $(CLEAN_PYTHON) \
		scripts/build_st1704_self_hosted_theme.py --package

tests:
	cd "$(REPOSITORY_ROOT)" && TMPDIR=/tmp TEMP=/tmp TMP=/tmp \
		"$(MANAGED_PYTHON)" -m pytest -p no:cacheprovider -q tests/st1704

cli-help:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/st1704_self_hosted_editorial_pilot.py --help

source-cli-help:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/st1704_official_source_capture.py --help
