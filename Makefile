.PHONY: help dev install lint format test deploy logs status restart \
       firmware-dev firmware-build firmware-upload firmware-monitor firmware-config firmware-uploadfs firmware-clean
.DEFAULT_GOAL := help

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

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

# --- Firmware (M5Stack AtomS3R) ---

firmware-dev: ## Run web UI dev server with mock data
	uv run python firmware/web/dev_server.py

firmware-build: ## Build ESP32 firmware
	cd firmware && pio run

firmware-upload: ## Build and flash firmware to M5Stack via USB
	cd firmware && pio run --target upload

firmware-monitor: ## Open serial monitor (115200 baud)
	cd firmware && pio device monitor

firmware-config: ## Generate firmware config from config.toml
	uv run python firmware/scripts/toml2json.py config.toml $(FAN) > firmware/data/config.json
	@echo "Written firmware/data/config.json — edit wifi_ssid/wifi_password before uploading"

firmware-uploadfs: ## Upload LittleFS filesystem (config) to M5Stack
	cd firmware && pio run --target uploadfs

firmware-clean: ## Clean PlatformIO build artifacts
	cd firmware && pio run --target clean
