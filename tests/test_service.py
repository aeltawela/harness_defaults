"""Verify a real background server discovers newly installed skills without a UI save."""
from pathlib import Path
import os
import subprocess
import sys
import time


def test_background_service_handles_new_skill_and_vendor_update(tmp_path):
    home=tmp_path/'home';state=tmp_path/'state'
    env=dict(os.environ,PYTHONPATH=str(Path(__file__).resolve().parents[1]))
    proc=subprocess.Popen([sys.executable,'-m','harness_defaults','--home',str(home),'--state',str(state),'serve','--port','0','--interval','3'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
    def wait_for(predicate):
        deadline=time.monotonic()+16
        while time.monotonic()<deadline:
            assert proc.poll() is None
            if predicate():return
            time.sleep(.15)
        raise AssertionError('Background reconciliation did not finish')
    try:
        wait_for(lambda:(state/'server.json').exists())
        path=home/'.claude/skills/new/SKILL.md';path.parent.mkdir(parents=True)
        path.write_text('---\nname: new\n---\nFirst version.\n')
        wait_for(lambda:'disable-model-invocation: true' in path.read_text())
        path.write_text('---\nname: new\n---\nVendor update.\n')
        wait_for(lambda:'disable-model-invocation: true' in path.read_text())
        assert path.read_text().endswith('Vendor update.\n')
    finally:
        proc.terminate();proc.wait(timeout=5)
