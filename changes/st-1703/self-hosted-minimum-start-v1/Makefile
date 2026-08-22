# Owner-local entry points for ST-1703 SELF_HOSTED_MINIMUM_START_V1.
# Invoke from the repository root with:
#   make -f changes/st-1703/self-hosted-minimum-start-v1/Makefile <target>

override SELF_HOSTED_MAKE_SHORT_FLAGS := $(firstword $(MAKEFLAGS))
ifneq ($(filter -%,$(SELF_HOSTED_MAKE_SHORT_FLAGS)),)
override SELF_HOSTED_MAKE_SHORT_FLAGS :=
endif
override SELF_HOSTED_UNSAFE_MAKE_MODES := $(strip $(foreach flag,e i n t,$(if $(findstring $(flag),$(SELF_HOSTED_MAKE_SHORT_FLAGS)),$(flag))))

ifeq ($(origin MAKEFLAGS),command line)
$(error Direct MAKEFLAGS assignments are not allowed for owner-local gates)
endif
ifneq ($(strip $(MAKEFILES)),)
$(error Preloaded MAKEFILES are not allowed for owner-local gates)
endif
ifneq ($(SELF_HOSTED_UNSAFE_MAKE_MODES),)
$(error Refusing non-verifying GNU Make mode(s): $(SELF_HOSTED_UNSAFE_MAKE_MODES))
endif

override SHELL := /usr/bin/busybox
override .SHELLFLAGS := sh -eu -o pipefail -c

override SELF_HOSTED_MAKEFILE := $(lastword $(MAKEFILE_LIST))
override SELF_HOSTED_SOURCE_ROOT := $(abspath $(dir $(SELF_HOSTED_MAKEFILE))/../../..)
override OWNER_REPOSITORY_ROOT := /home/minami/rakuten
override OWNER_LAUNCHER := $(OWNER_REPOSITORY_ROOT)/scripts/self_hosted_wordpress_python.sh
override MANAGED_PYTHON := $(OWNER_REPOSITORY_ROOT)/.venv/bin/python
override ROOT_OWNED_RUNTIME_GENERATOR_PYTHON := /usr/bin/python3.10

.PHONY: help doctor install-credentials create-draft \
	runtime-manifest-generate runtime-manifest-check \
	theme-source-check theme-package theme-check

help:
	@echo 'Offline: doctor runtime-manifest-check theme-source-check theme-check'
	@echo 'Local maintenance: runtime-manifest-generate'
	@echo 'Human gated: install-credentials create-draft theme-package'

doctor:
	"$(OWNER_LAUNCHER)" doctor

install-credentials:
	"$(OWNER_LAUNCHER)" install-credentials

create-draft:
	"$(OWNER_LAUNCHER)" create-draft

runtime-manifest-generate:
	cd "$(SELF_HOSTED_SOURCE_ROOT)" && \
		/usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC \
		"$(ROOT_OWNED_RUNTIME_GENERATOR_PYTHON)" \
		-B -I -S -X pycache_prefix=/dev/null \
		scripts/build_st1703_self_hosted_runtime_manifest.py

runtime-manifest-check:
	cd "$(SELF_HOSTED_SOURCE_ROOT)" && \
		/usr/bin/busybox env -i PATH=/usr/bin:/bin LANG=C LC_ALL=C TZ=UTC \
		"$(ROOT_OWNED_RUNTIME_GENERATOR_PYTHON)" \
		-B -I -S -X pycache_prefix=/dev/null \
		scripts/build_st1703_self_hosted_runtime_manifest.py --check

theme-source-check:
	cd "$(SELF_HOSTED_SOURCE_ROOT)" && \
		"$(MANAGED_PYTHON)" -B -I -S -X pycache_prefix=/dev/null \
		scripts/build_st1703_self_hosted_theme.py --source-check

theme-package:
	cd "$(SELF_HOSTED_SOURCE_ROOT)" && \
		"$(MANAGED_PYTHON)" -B -I -S -X pycache_prefix=/dev/null \
		scripts/build_st1703_self_hosted_theme.py --package

theme-check:
	cd "$(SELF_HOSTED_SOURCE_ROOT)" && \
		"$(MANAGED_PYTHON)" -B -I -S -X pycache_prefix=/dev/null \
		scripts/build_st1703_self_hosted_theme.py --check
