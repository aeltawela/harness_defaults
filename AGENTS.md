# Agent instructions

## Privacy boundary

This is a public repository. Do not add personal, account-specific, or machine-specific information to commits, pull requests, issues, documentation, fixtures, screenshots, logs, or generated artifacts.

Never commit or quote:

- Home-directory paths, usernames, hostnames, device names, local project names, or filesystem inventories.
- Installed skills, plugins, extension lists, policy exports, application-support state, backups, caches, or service logs from a real machine.
- Credentials, tokens, cookies, API keys, private URLs, repository remotes, or other secrets.
- Screenshots or recordings of a real local environment.

Use temporary directories and invented skill/plugin names in tests and documentation. Screenshot examples must be generated from synthetic fixtures and must state that they contain no real local inventory data.

Before committing, inspect the staged diff for accidental personal or local-environment details. If a change needs real-environment verification, report only aggregate, non-identifying results and keep raw evidence outside this repository.
