# Repository-local gates for ST-1506 SELF_HOSTED_WORDPRESS_OPERATOR_BRIDGE_V1.
# Invoke from the repository root with:
#   make -f changes/st-1506/self-hosted-wordpress-operator-bridge-v1/Makefile <target>

override OPERATOR_MAKE_SHORT_FLAGS := $(firstword $(MAKEFLAGS))
ifneq ($(filter -%,$(OPERATOR_MAKE_SHORT_FLAGS)),)
override OPERATOR_MAKE_SHORT_FLAGS :=
endif
override OPERATOR_UNSAFE_MAKE_MODES := $(strip $(foreach flag,e i n t,$(if $(findstring $(flag),$(OPERATOR_MAKE_SHORT_FLAGS)),$(flag))))

ifeq ($(origin MAKEFLAGS),command line)
$(error Direct MAKEFLAGS assignments are not allowed for repository-local gates)
endif
ifneq ($(strip $(MAKEFILES)),)
$(error Preloaded MAKEFILES are not allowed for repository-local gates)
endif
ifneq ($(OPERATOR_UNSAFE_MAKE_MODES),)
$(error Refusing non-verifying GNU Make mode(s): $(OPERATOR_UNSAFE_MAKE_MODES))
endif

override SHELL := /usr/bin/busybox
override .SHELLFLAGS := sh -eu -o pipefail -c
override OPERATOR_MAKEFILE := $(lastword $(MAKEFILE_LIST))
override REPOSITORY_ROOT := $(abspath $(dir $(OPERATOR_MAKEFILE))/../../..)
override GIT_COMMON_DIRECTORY := $(strip $(shell cd "$(REPOSITORY_ROOT)" && /usr/bin/git rev-parse --path-format=absolute --git-common-dir))
ifeq ($(GIT_COMMON_DIRECTORY),)
$(error Git common directory is unavailable)
endif
override MANAGED_PYTHON := $(abspath $(GIT_COMMON_DIRECTORY)/../.venv/bin/python)
override OPERATOR_LAUNCHER := $(REPOSITORY_ROOT)/scripts/st1506_wordpress_operator_python.sh
override CLEAN_PYTHON := /usr/bin/env -i PATH=/usr/bin:/bin \
	LANG=C LC_ALL=C TZ=UTC \
	$(MANAGED_PYTHON) -B -I -S -X pycache_prefix=/dev/null

.PHONY: help check manifest-generate manifest-check plugin-check plugin-package \
	plugin-source-check tests cli-help

help:
	@echo 'Offline: check manifest-check plugin-check plugin-source-check tests cli-help'
	@echo 'Owner-private artifact: manifest-generate plugin-package'
	@echo 'No target performs a live WordPress request, approval, activation, or publication'

check: manifest-check plugin-check tests

manifest-generate:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1506_wordpress_operator.py --manifest

manifest-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1506_wordpress_operator.py --check

plugin-source-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1506_wordpress_operator.py --source-check

plugin-check:
	cd "$(REPOSITORY_ROOT)" && $(CLEAN_PYTHON) \
		scripts/build_st1506_wordpress_operator.py --package-check

plugin-package:
	cd "$(REPOSITORY_ROOT)" && umask 0077 && $(CLEAN_PYTHON) \
		scripts/build_st1506_wordpress_operator.py --package

tests:
	cd "$(REPOSITORY_ROOT)" && TMPDIR=/tmp TEMP=/tmp TMP=/tmp \
		PYTHONDONTWRITEBYTECODE=1 "$(MANAGED_PYTHON)" -m pytest \
		-p no:cacheprovider -q -s tests/st1506_operator

cli-help:
	cd "$(REPOSITORY_ROOT)" && "$(OPERATOR_LAUNCHER)" --help
