.PHONY: check test inventory-plan inventory-scan

PYTHON ?= python3
INVENTORY_PROFILE ?= cambridge-agent-inventory
INVENTORY_SERVICES = --service ec2 --service vpc --service rds --service ecs --service dynamodb --service sqs --service cloudformation --service s3

check:
	$(PYTHON) -B scripts/check_repo.py
	$(PYTHON) -B -m unittest discover -s tests -v
	$(PYTHON) -B -m unittest discover -s infrastructure/agent-executor -p 'test_*.py' -v

test:
	$(PYTHON) -B -m unittest discover -s tests -v
	$(PYTHON) -B -m unittest discover -s infrastructure/agent-executor -p 'test_*.py' -v

inventory-plan:
	$(PYTHON) -B scripts/aws_inventory.py plan --account cambridge-tcg --profile "$(INVENTORY_PROFILE)" $(INVENTORY_SERVICES)

inventory-scan:
	$(PYTHON) -B scripts/aws_inventory.py scan --account cambridge-tcg --profile "$(INVENTORY_PROFILE)" $(INVENTORY_SERVICES)
