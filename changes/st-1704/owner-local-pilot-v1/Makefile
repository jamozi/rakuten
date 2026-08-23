# Owner-local entry points for ST1704_OWNER_LOCAL_PILOT_LEDGER_V1.
# Invoke from the exact physical repository root.

override ST1704_MAKE_SHORT_FLAGS := $(firstword $(MAKEFLAGS))
ifneq ($(filter -%,$(ST1704_MAKE_SHORT_FLAGS)),)
override ST1704_MAKE_SHORT_FLAGS :=
endif
override ST1704_UNSAFE_MAKE_MODES := $(strip $(foreach flag,e i n t,$(if $(findstring $(flag),$(ST1704_MAKE_SHORT_FLAGS)),$(flag))))

ifeq ($(origin MAKEFLAGS),command line)
$(error Direct MAKEFLAGS assignments are not allowed for owner-local gates)
endif
ifneq ($(strip $(MAKEFILES)),)
$(error Preloaded MAKEFILES are not allowed for owner-local gates)
endif
ifneq ($(ST1704_UNSAFE_MAKE_MODES),)
$(error Refusing non-verifying GNU Make mode(s): $(ST1704_UNSAFE_MAKE_MODES))
endif

override SHELL := /usr/bin/busybox
override .SHELLFLAGS := sh -eu -o pipefail -c
override ST1704_MAKEFILE := $(lastword $(MAKEFILE_LIST))
override ST1704_ROOT := $(abspath $(dir $(ST1704_MAKEFILE))/../../..)
override ST1704_PYTHON := /home/minami/rakuten/.venv/bin/python
override ST1704_ENV := /usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC
override ST1704_PYTHON_FLAGS := -B -I -S -X pycache_prefix=/dev/null
override ST1704_CLI := $(ST1704_ROOT)/scripts/st1704_owner_local_pilot.py
override ST1704_GENERATOR := $(ST1704_ROOT)/scripts/build_st1704_owner_local_pilot.py

.PHONY: help doctor init record report generate check test

help:
	@echo 'Read-only: doctor report check test'
	@echo 'Owner-local writes: init record'
	@echo 'Repository maintenance: generate'

doctor:
	cd "$(ST1704_ROOT)" && $(ST1704_ENV) "$(ST1704_PYTHON)" $(ST1704_PYTHON_FLAGS) "$(ST1704_CLI)" doctor

init:
	cd "$(ST1704_ROOT)" && $(ST1704_ENV) "$(ST1704_PYTHON)" $(ST1704_PYTHON_FLAGS) "$(ST1704_CLI)" init

record:
	cd "$(ST1704_ROOT)" && $(ST1704_ENV) "$(ST1704_PYTHON)" $(ST1704_PYTHON_FLAGS) "$(ST1704_CLI)" record

report:
	cd "$(ST1704_ROOT)" && $(ST1704_ENV) "$(ST1704_PYTHON)" $(ST1704_PYTHON_FLAGS) "$(ST1704_CLI)" report

generate:
	cd "$(ST1704_ROOT)" && $(ST1704_ENV) "$(ST1704_PYTHON)" $(ST1704_PYTHON_FLAGS) "$(ST1704_GENERATOR)"

check:
	cd "$(ST1704_ROOT)" && $(ST1704_ENV) "$(ST1704_PYTHON)" $(ST1704_PYTHON_FLAGS) "$(ST1704_GENERATOR)" --check

test:
	cd "$(ST1704_ROOT)" && /usr/bin/busybox env -i PATH=/usr/bin:/bin \
		LANG=C LC_ALL=C TZ=UTC "$(ST1704_PYTHON)" -B -I \
		-m pytest -p no:cacheprovider -q tests/st1704
