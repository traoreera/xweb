
# ============================================================
# 📚 HELP
# ============================================================
help: ## Afficher la liste des commandes disponibles
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'


# ============================================================
# 📦 Installation & initialisation
# ============================================================
install: ## Installer les dépendances via Poetry
	@uv lock
	@uv sync



# ===========================================================
# 🧪 Tests — ciblés sur xcore/
# ============================================================
test: ## Lancer les tests unitaires de xcore/
	@echo "🧪 Tests unitaires (xcore/)..."
	@uv run pytest tests/ -q -vv || { \
		if [ "$(STRICT)" = "1" ]; then exit 1; \
		else echo "[WARN] Échec ignoré (STRICT=0)"; fi; \
	}

test-cov: ## Tests avec couverture de code (xcore/)
	@echo "🧪 Tests + couverture..."
	@uv run pytest tests/ --cov=xcore --cov-branch --cov-report=term-missing --cov-report=xml

# ============================================================
# 🧹 Nettoyage
# ============================================================
clean: ## Supprimer __pycache__, *.pyc, *.pyo
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null; true
	@find . -type f \( -name "*.pyc" -o -name "*.pyo" -o -name "*.backup" \) -exec rm -f {} +

.PHONY: help test test-cov lint-check lint-fix docs clean
