"""The public command opens the shared harness-config dashboard."""
import sys
from harness_defaults.__main__ import main


def test_ui_opens_shared_dashboard(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr('os.execvp', lambda binary, args: calls.append((binary, args)))
    entry=tmp_path/'manager.mjs';entry.write_text('// fixture')
    monkeypatch.setenv('HARNESS_CONFIG_MANAGER_ENTRY',str(entry))
    monkeypatch.setattr(sys, 'argv', ['harness-config', '--state', str(tmp_path), 'ui'])
    assert main() is None
    assert calls == [('node', ['node',str(entry),'web', '--view', 'harness'])]


def test_one_command_dispatches_model_management(tmp_path, monkeypatch):
    calls=[]
    entry=tmp_path/'manager.mjs';entry.write_text('// fixture')
    monkeypatch.setenv('HARNESS_CONFIG_MANAGER_ENTRY',str(entry))
    monkeypatch.setattr('os.execvp',lambda binary,args:calls.append((binary,args)))
    monkeypatch.setattr(sys,'argv',['harness-config','config','help'])
    assert main()==0
    assert calls==[('node',['node',str(entry),'config','help'])]


def test_default_opens_dashboard(tmp_path, monkeypatch):
    calls=[]
    entry=tmp_path/'manager.mjs';entry.write_text('// fixture')
    monkeypatch.setenv('HARNESS_CONFIG_MANAGER_ENTRY',str(entry))
    monkeypatch.setattr('os.execvp',lambda binary,args:calls.append((binary,args)))
    monkeypatch.setattr(sys,'argv',['harness-config'])
    assert main() is None
    assert calls==[('node',['node',str(entry),'web','--view','harness'])]
