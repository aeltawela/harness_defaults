#!/usr/bin/env python3
"""Install only this manager's files, launcher, and user LaunchAgent."""
import argparse
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import subprocess
import sys

LABEL='local.harness_defaults'

def main():
    p=argparse.ArgumentParser();p.add_argument('--uninstall-service',action='store_true');p.add_argument('--no-start',action='store_true');a=p.parse_args()
    home=Path.home();base=home/'Library/Application Support/harness_defaults';plist=home/'Library/LaunchAgents'/f'{LABEL}.plist'
    domain=f'gui/{os.getuid()}'
    if a.uninstall_service:
        subprocess.run(['launchctl','bootout',domain+'/'+LABEL],capture_output=True)
        if plist.exists():plist.unlink()
        print('Background service removed. Choices, backups, and program remain available.');return
    uv=shutil.which('uv')
    if not uv:raise SystemExit('uv is required to create the isolated Python environment. Install uv, then rerun this installer.')
    source=Path(__file__).resolve().parent
    base.mkdir(parents=True,exist_ok=True);base.chmod(0o700)
    app=base/'app';app.mkdir(exist_ok=True)
    shutil.copytree(source/'harness_defaults',app/'harness_defaults',dirs_exist_ok=True,ignore=shutil.ignore_patterns('__pycache__'))
    for name in ['requirements.txt','README.md','install.py']:shutil.copy2(source/name,app/name)
    venv=base/'venv'
    if not (venv/'bin/python').exists():subprocess.run([uv,'venv','--python','3.13',str(venv)],check=True)
    subprocess.run([uv,'pip','install','--python',str(venv/'bin/python'),'-r',str(app/'requirements.txt')],check=True)
    launcher=home/'.local/bin/harness_defaults';launcher.parent.mkdir(parents=True,exist_ok=True)
    launcher.write_text('#!/bin/sh\nexec env '+shlex.quote('PYTHONPATH='+str(app))+' '+shlex.quote(str(venv/'bin/python'))+' -m harness_defaults "$@"\n');launcher.chmod(0o755)
    # Migrate earlier names without losing policy or original-byte backups.
    legacy_bases=[
        home/'Library/Application Support/plugins_defaults',
        home/'Library/Application Support/Invocation Manager',
    ]
    legacy_plists=[
        home/'Library/LaunchAgents/local.plugins_defaults.plist',
        home/'Library/LaunchAgents/local.invocation-manager.plist',
    ]
    state=base/'state'
    for label,plist_path in [('local.plugins_defaults',legacy_plists[0]),('local.invocation-manager',legacy_plists[1])]:
        if plist_path.exists():subprocess.run(['launchctl','bootout',domain+'/'+label],capture_output=True)
    if not state.exists():
        for legacy_base in legacy_bases:
            if (legacy_base/'state').is_dir():
                shutil.copytree(legacy_base/'state',state,ignore=shutil.ignore_patterns('server.json','lock','service.log','service-error.log'))
                break
    state.mkdir(exist_ok=True);state.chmod(0o700)
    for name in ['service.log','service-error.log']:
        (state/name).touch(exist_ok=True);(state/name).chmod(0o600)
    config={'Label':LABEL,'ProgramArguments':[str(venv/'bin/python'),'-m','harness_defaults','serve'],
            'EnvironmentVariables':{'PYTHONPATH':str(app)},'RunAtLoad':True,'KeepAlive':True,'ThrottleInterval':30,
            'StandardOutPath':str(state/'service.log'),'StandardErrorPath':str(state/'service-error.log'),
            'ProcessType':'Background'}
    plist.parent.mkdir(parents=True,exist_ok=True)
    plist.write_bytes(plistlib.dumps(config));plist.chmod(0o600)
    subprocess.run([str(launcher),'scan'],check=True)
    if not a.no_start:
        subprocess.run(['launchctl','bootout',domain+'/'+LABEL],capture_output=True)
        subprocess.run(['launchctl','enable',domain+'/'+LABEL],check=True)
        subprocess.run(['launchctl','bootstrap',domain,str(plist)],check=True)
        for plist_path in legacy_plists:
            if plist_path.exists():plist_path.unlink()
    for legacy_launcher in [home/'.local/bin/plugins_defaults',home/'.local/bin/invocation-manager']:
        if legacy_launcher.exists():
            legacy_launcher.write_text('#!/bin/sh\nexec '+shlex.quote(str(launcher))+' "$@"\n')
            legacy_launcher.chmod(0o755)
    print('Installed '+str(launcher))
    print('Open the checkbox list: harness_defaults ui')

if __name__=='__main__':main()
