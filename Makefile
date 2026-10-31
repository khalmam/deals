.PHONY: install test lint run
install:
	pip install -r requirements-dev.txt
test:
	python -m pytest -q
lint:
	ruff check .
run:
	python manage.py runserver 8000
