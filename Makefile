.PHONY: test test-real

test:
	@.venv/bin/python -m unittest discover -s tests

test-real:
	@PWNINIT_E2E_REAL=1 .venv/bin/python -m unittest discover -s tests
