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

.PHONY: help check manifest-generate manifest-check theme-navigation-generate \
	theme-navigation-check theme-assets-generate theme-assets-check theme-source-check \
	theme-check theme-package tests cli-help source-cli-help \
	rakuten-capture-manifest-generate rakuten-capture-manifest-check \
	rakuten-capture-cli-help

help:
	@echo 'Offline: check manifest-check rakuten-capture-manifest-check theme-navigation-check theme-assets-check theme-source-check theme-check tests cli-help source-cli-help rakuten-capture-cli-help'
	@echo 'Local artifacts: manifest-generate rakuten-capture-manifest-generate theme-navigation-generate theme-assets-generate theme-package'
	@echo 'Article operations: use the five closed subcommands shown by cli-help'
	@echo 'Read-only source capture: use the two closed subcommands shown by source-cli-help'
	@echo 'Owner-authorized Rakuten capture: use the one closed subcommand shown by rakuten-capture-cli-help'
	@echo 'Operational process: repository-root CLEAN_PYTHON only (-B -I -S; ambient environment removed)'

check: manifest-check rakuten-capture-manifest-check theme-navigation-check theme-assets-check theme-source-check theme-check tests

manifest-generate:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1704_self_hosted_editorial_manifest.py

manifest-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1704_self_hosted_editorial_manifest.py --check

rakuten-capture-manifest-generate:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1704_rakuten_capture_manifest.py

rakuten-capture-manifest-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1704_rakuten_capture_manifest.py --check

theme-navigation-generate:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_editorial_v3_theme_navigation.py

theme-navigation-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_editorial_v3_theme_navigation.py --check

theme-assets-generate:
	cd "$(REPOSITORY_ROOT)" && $(MANAGED_PYTHON) \
		scripts/build_st1704_theme_assets.py

theme-assets-check:
	cd "$(REPOSITORY_ROOT)" && $(MANAGED_PYTHON) \
		scripts/build_st1704_theme_assets.py --check

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

rakuten-capture-cli-help:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/st1704_rakuten_product_capture.py --help
