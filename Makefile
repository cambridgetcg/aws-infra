.PHONY: check test inventory-plan

PYTHON ?= python3

check:
	$(PYTHON) -B scripts/check_repo.py
	$(PYTHON) -B -m unittest discover -s tests -v
	$(PYTHON) -B -m unittest discover -s infrastructure/agent-executor -p 'test_*.py' -v

test:
	$(PYTHON) -B -m unittest discover -s tests -v
	$(PYTHON) -B -m unittest discover -s infrastructure/agent-executor -p 'test_*.py' -v

inventory-plan:
	$(PYTHON) -B scripts/aws_inventory.py plan --account cambridge-tcg --profile default
