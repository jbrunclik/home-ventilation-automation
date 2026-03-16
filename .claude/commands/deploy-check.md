Verify deployment readiness:

1. Run `make lint && make test` to ensure code quality
2. Check that `config.toml` exists (not just `config.example.toml`)
3. Check that `.env` exists with required variables
4. Verify the systemd service file is correct
5. Show the user what `make deploy` will do before they run it

Report status of each check.
