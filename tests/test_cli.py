"""The public UI command opens the shared Model Bridge dashboard."""
import sys
from harness_defaults.__main__ import main


def test_ui_opens_shared_dashboard(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('os.execvp', lambda binary, args: calls.append((binary, args)))
    monkeypatch.setattr(sys, 'argv', ['harness-config', '--state', str(tmp_path), 'ui'])
    assert main() is None
    assert calls == [('model-bridge', ['model-bridge', 'web', '--view', 'harness'])]
