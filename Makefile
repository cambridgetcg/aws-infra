.PHONY: check test inventory-plan

PYTHON ?= python3

check:
	$(PYTHON) -B scripts/check_repo.py
	$(PYTHON) -B -m unittest discover -s tests -v

test:
	$(PYTHON) -B -m unittest discover -s tests -v

inventory-plan:
	$(PYTHON) -B scripts/aws_inventory.py plan --account cambridge-tcg --profile default
