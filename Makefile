# Makefile pour INIS — Commandes de développement, tests et exploitation
# Conforme à ARCHITECTURE.md §1.2

.PHONY: help install dev test test-unit test-integration test-api lint format \
        check-architecture check-contracts check-invariants check-compat check-all \
        migrate migrate-rollback run seed export-openapi changelog certs benchmark clean

PYTHON ?= python
PIP ?= pip
ALEMBIC ?= $(PYTHON) -m alembic
PYTEST ?= $(PYTHON) -m pytest
RUFF ?= $(PYTHON) -m ruff

help:
	@echo "Commandes disponibles dans INIS :"
	@echo "  install            Installe le package en mode éditable avec dépendances dev"
	@echo "  dev                Lance l'API FastAPI en mode développement (reload)"
	@echo "  run                Lance l'API via python main.py"
	@echo "  test               Lance la suite de tests complète (pytest -q)"
	@echo "  test-unit          Lance uniquement les tests unitaires"
	@echo "  test-integration   Lance uniquement les tests d'intégration"
	@echo "  test-api           Lance uniquement les tests de l'API HTTP"
	@echo "  lint               Vérifie le code avec Ruff"
	@echo "  format             Formate le code avec Ruff"
	@echo "  check-architecture Vérifie les invariants d'architecture (§37)"
	@echo "  check-contracts    Vérifie les contrats entre modules"
	@echo "  check-invariants   Vérifie les invariants §0.2"
	@echo "  check-compat       Vérifie la compatibilité ascendante des migrations (§41.14)"
	@echo "  check-all          Exécute toutes les portes de qualité statiques"
	@echo "  migrate            Applique les migrations Alembic (upgrade head)"
	@echo "  migrate-rollback   Rollback de la dernière migration Alembic (-1)"
	@echo "  seed               Injecte un jeu de données de test/développement"
	@echo "  export-openapi     Exporte openapi.json depuis l'application FastAPI"
	@echo "  changelog          Génère docs/changelog.json depuis migrations et git"
	@echo "  certs              Génère les certificats mTLS pour les agents (§19)"
	@echo "  benchmark          Lance les benchmarks de performance (§41.13)"
	@echo "  clean              Nettoie les caches et fichiers temporaires"

install:
	$(PIP) install -e .[dev]

dev:
	$(PYTHON) -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

run:
	$(PYTHON) main.py

test:
	$(PYTEST) -q

test-unit:
	$(PYTEST) tests/unit -q

test-integration:
	$(PYTEST) tests/integration -q

test-api:
	$(PYTEST) tests/api -q

lint:
	$(RUFF) check .

format:
	$(RUFF) format .

check-architecture:
	$(PYTHON) scripts/check_architecture.py

check-contracts:
	$(PYTHON) scripts/check_contracts.py

check-invariants:
	$(PYTHON) scripts/check_invariants.py

check-compat:
	$(PYTHON) scripts/check_backward_compat.py migrations/versions/

check-all: check-architecture check-contracts check-invariants check-compat lint

migrate:
	$(ALEMBIC) upgrade head

migrate-rollback:
	$(PYTHON) scripts/migrate_rollback.py

seed:
	$(PYTHON) scripts/seed_dev.py

export-openapi:
	$(PYTHON) scripts/export_openapi.py

changelog:
	$(PYTHON) scripts/generate_changelog.py

certs:
	sh scripts/generate_certs.sh

benchmark:
	$(PYTHON) scripts/benchmark.py

clean:
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true

