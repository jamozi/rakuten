PYTHON ?= .venv/bin/python

.PHONY: generate check init doctor record report test

generate:
	$(PYTHON) scripts/build_st1704_affiliate_learning.py

check:
	$(PYTHON) scripts/build_st1704_affiliate_learning.py --check

init:
	$(PYTHON) scripts/st1704_affiliate_learning.py init

doctor:
	$(PYTHON) scripts/st1704_affiliate_learning.py doctor

record:
	$(PYTHON) scripts/st1704_affiliate_learning.py record

report:
	$(PYTHON) scripts/st1704_affiliate_learning.py report

test:
	$(PYTHON) -m pytest -p no:cacheprovider -q tests/st1704/test_affiliate_learning_v2.py
