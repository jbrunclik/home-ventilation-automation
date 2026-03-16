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

deploy: ## Deploy config, systemd unit, enable service
	mkdir -p ~/.config/home-ventilation
	cp config.toml ~/.config/home-ventilation/config.toml
	cp .env ~/.config/home-ventilation/.env
	chmod 600 ~/.config/home-ventilation/.env
	mkdir -p ~/.config/systemd/user
	cp systemd/home-ventilation.service ~/.config/systemd/user/
	systemctl --user daemon-reload
	systemctl --user enable --now home-ventilation

logs: ## Follow journald logs
	journalctl --user -u home-ventilation -f

status: ## Show systemctl status
	systemctl --user status home-ventilation

restart: ## Restart the service
	systemctl --user restart home-ventilation
