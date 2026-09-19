# harness_defaults

**Make automatic agent behavior an intentional default.**

`harness_defaults` gives local Codex, Qwen Code, and Claude Code skills one simple rule: new skills are explicit-only until you choose otherwise. Its local checkbox UI lets you keep a small trusted core implicit and control every other discovered skill, including skills brought in by plugin and extension updates.

It runs entirely on your Mac. There is no cloud service, analytics, or account connection.

## Install

`uv` manages the isolated Python environment automatically. Install it first if needed: <https://docs.astral.sh/uv/getting-started/installation/>.

```sh
git clone https://github.com/aeltawela/harness_defaults.git
cd harness_defaults
python3 install.py
```

The installer makes `harness_defaults` available in your normal terminals at `~/.local/bin/harness_defaults` and starts a user-level macOS service that checks for new or updated skills every 15 seconds.

If `~/.local/bin` is not already on your `PATH`, add this once to `~/.zshrc`:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Then open the controls from any terminal:

```sh
harness_defaults ui
```

## The one rule

| Checkbox | Meaning |
| --- | --- |
| Checked | The skill requires an explicit invocation. |
| Unchecked | The host may invoke it automatically. |

New skills are checked by default. Group controls apply a default to a plugin or extension; individual choices override a group default. The initial core preset keeps the existing Codex system skills implicit, and you can change it in the UI.

## Terminal commands

```sh
harness_defaults ui                 # open the checkbox UI
harness_defaults status             # see coverage and problems
harness_defaults scan               # dry run; no files changed
harness_defaults apply              # reconcile now
harness_defaults pause              # stop background changes
harness_defaults resume             # resume background changes
harness_defaults export             # print your policy JSON
harness_defaults add-project /path/to/project
harness_defaults restore            # restore manager-owned metadata changes
```

`harness_defaults launch -- qwen` synchronizes choices immediately before launching an agent CLI.

## What it changes

| Host | Managed metadata |
| --- | --- |
| Codex | `agents/openai.yaml` → `policy.allow_implicit_invocation` |
| Qwen Code | `SKILL.md` → `disable-model-invocation` |
| Claude Code | `SKILL.md` → `disable-model-invocation` |

The manager preserves unrelated YAML keys, comments, and skill bodies. It journals the original bytes before a change and will not restore over later vendor or user edits.

It discovers local user skills, locally installed plugin and extension skill directories, and skills in project directories you explicitly register. Plugin tools, hooks, extension context files, hosted ChatGPT/claude.ai settings, and already-open agent conversations use separate mechanisms and are shown or documented as such; they are not silently treated as skill invocation policy.

## Contributing

Contributions are welcome. Bug reports, host-adapter improvements, portability work, tests, and UX refinements are all useful.

1. Fork the repository and create a focused branch.
2. Add or update the relevant test.
3. Run the documented development test command below.
4. Open a pull request describing the host/version behavior you checked.

Please do not include real skill contents, account tokens, application-support state, or private plugin caches in issues or pull requests.

## Development

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt pytest playwright
.venv/bin/python -m pytest
```

The browser tests need Playwright Chromium once:

```sh
.venv/bin/python -m playwright install chromium
```

## License

MIT. See [LICENSE](LICENSE).
