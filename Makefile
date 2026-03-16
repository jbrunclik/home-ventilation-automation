.PHONY: dev install lint format test deploy logs status restart

dev:
	uv sync

install:
	uv sync --no-dev

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff format .
	uv run ruff check --fix .

test:
	uv run pytest tests/ -v

deploy:
	mkdir -p ~/.config/home-ventilation
	cp config.toml ~/.config/home-ventilation/config.toml
	cp .env ~/.config/home-ventilation/.env
	chmod 600 ~/.config/home-ventilation/.env
	mkdir -p ~/.config/systemd/user
	cp systemd/home-ventilation.service ~/.config/systemd/user/
	systemctl --user daemon-reload
	systemctl --user enable --now home-ventilation

logs:
	journalctl --user -u home-ventilation -f

status:
	systemctl --user status home-ventilation

restart:
	systemctl --user restart home-ventilation
