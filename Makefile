.PHONY: help dev install lint format test deploy logs status restart
.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

dev: ## Install all deps (uv sync)
	uv sync

install: ## Install production deps only
	uv sync --no-dev

lint: ## Run ruff check + format check
	uv run ruff check .
	uv run ruff format --check .

format: ## Auto-format and fix lint issues
	uv run ruff format .
	uv run ruff check --fix .

test: ## Run pytest
	uv run pytest tests/ -v

deploy: ## Deploy systemd unit (config stays in repo), enable service
	chmod 600 .env
	mkdir -p ~/.config/systemd/user
	sed 's|@REPO_DIR@|$(CURDIR)|g' systemd/home-ventilation.service > ~/.config/systemd/user/home-ventilation.service
	systemctl --user daemon-reload
	systemctl --user enable --now home-ventilation

logs: ## Follow journald logs
	journalctl --user -u home-ventilation -f

status: ## Show systemctl status
	systemctl --user status home-ventilation

restart: ## Restart the service
	systemctl --user restart home-ventilation
