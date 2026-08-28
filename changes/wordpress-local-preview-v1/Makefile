SHELL := /usr/bin/bash
.SHELLFLAGS := -eu -o pipefail -c

REPOSITORY_ROOT := $(abspath ../..)
PYTHON := $(REPOSITORY_ROOT)/.venv/bin/python

.PHONY: help check tests

help:
	@echo 'Runtime commands are exposed from the repository root as wordpress-preview-* targets.'
	@echo 'Offline verification: make -C changes/wordpress-local-preview-v1 check'

check: tests

tests:
	cd "$(REPOSITORY_ROOT)" && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp \
		"$(PYTHON)" -m pytest -s -p no:cacheprovider -q tests/wordpress_local_preview
