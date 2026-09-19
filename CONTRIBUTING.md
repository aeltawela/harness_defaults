# Contributing to harness_defaults

Thank you for considering a contribution. Small, well-tested changes are ideal.

## Before opening a pull request

- Keep each change focused on one behavior or host integration.
- Add a regression test for any bug fix.
- Run the full test suite locally.
- State the host and version you tested in the pull request.
- Do not commit private configuration, skill content, cache directories, screenshots of sensitive data, tokens, or manager state.

## Development setup

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt pytest playwright
.venv/bin/python -m pytest
```

The project is open for contributions under the MIT License.
