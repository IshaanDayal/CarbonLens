.PHONY: help install setup run-django run-docker stop-docker clean download-data test

help:
	@echo "CarbonLens - Makefile Commands"
	@echo "=============================="
	@echo "  make install      - Install dependencies"
	@echo "  make setup        - Full setup (install + download data + migrate)"
	@echo "  make run-django    - Start Django backend"
	@echo "  make run-docker    - Start with Docker Compose"
	@echo "  make stop-docker   - Stop Docker Compose"
	@echo "  make download-data - Download OWID CO2 data"
	@echo "  make test         - Run tests"
	@echo "  make clean        - Clean Python cache files"

install:
	pip install -r requirements.txt

setup: install
	mkdir -p data
	python scripts/download_owid_data.py
	python manage.py migrate

run-django:
	python manage.py runserver



run-docker:
	docker-compose up -d

stop-docker:
	docker-compose down

download-data:
	python scripts/download_owid_data.py

test:
	python manage.py test

clean:
	find . -type d -name __pycache__ -exec rm -r {} +
	find . -type f -name "*.pyc" -delete
	find . -type f -name "*.pyo" -delete

