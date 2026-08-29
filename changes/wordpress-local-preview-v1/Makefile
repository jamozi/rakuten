SHELL := /usr/bin/bash
.SHELLFLAGS := -eu -o pipefail -c

REPOSITORY_ROOT := $(abspath ../..)
PYTHON := $(REPOSITORY_ROOT)/.venv/bin/python

.PHONY: help check materialize tests

help:
	@echo 'Runtime commands are exposed from the repository root as wordpress-preview-* targets.'
	@echo 'Offline verification: make -C changes/wordpress-local-preview-v1 check'
	@echo 'Owner-private fixture refresh: make -C changes/wordpress-local-preview-v1 materialize'

check: tests

materialize:
	cd "$(REPOSITORY_ROOT)" && PYTHONDONTWRITEBYTECODE=1 \
		"$(PYTHON)" scripts/raos_editorial_portfolio_v2.py materialize-local

tests:
	cd "$(REPOSITORY_ROOT)" && PYTHONDONTWRITEBYTECODE=1 TMPDIR=/tmp \
		"$(PYTHON)" -m pytest -s -p no:cacheprovider -q tests/wordpress_local_preview
