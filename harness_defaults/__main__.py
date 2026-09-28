import argparse
import json
import os
from pathlib import Path
import sys
import time
from .engine import Manager


def default_state():return Path.home()/'Library/Application Support/harness_defaults/state'


MODEL_COMMANDS={'help','web','tui','init','models','config','native-roles','doctor',
                'remote-ownership','update','install','upgrade','stage-cli',
                'install-cli-candidate','promote-cli','remote-daemon','rollback','cleanup'}


def open_manager(arguments):
    entry=Path(os.environ.get('HARNESS_CONFIG_MANAGER_ENTRY',
        Path.home()/'.local/share/harness-config/manager.mjs'))
    if not entry.is_file():
        raise ValueError('Model controls are not installed. Install the Harness Config model component first.')
    os.execvp('node',['node',str(entry),*arguments])


def main():
    if len(sys.argv)>1 and sys.argv[1] in MODEL_COMMANDS:
        try:open_manager(sys.argv[1:])
        except (ValueError,OSError) as e:print(str(e),file=sys.stderr);return 1
        return 0
    parser=argparse.ArgumentParser(description='Manage model routes and local skill invocation choices for Codex, Qwen Code, and Claude Code.',
        epilog='Model commands: config, models, doctor, update, install, upgrade, rollback. Run harness-config config help for endpoint and model options.')
    parser.add_argument('--state',type=Path,default=default_state(),help='Policy and backup directory')
    parser.add_argument('--home',type=Path,default=Path.home(),help='Home to discover (useful for isolated testing)')
    sub=parser.add_subparsers(dest='command')
    for name in ['status','scan','apply','export','restore','pause','resume']:
        p=sub.add_parser(name);p.add_argument('--json',action='store_true')
    p=sub.add_parser('watch');p.add_argument('--interval',type=int,default=15)
    p=sub.add_parser('serve');p.add_argument('--port',type=int,default=47831);p.add_argument('--interval',type=int,default=15);p.add_argument('--open',action='store_true')
    sub.add_parser('ui')
    p=sub.add_parser('add-project');p.add_argument('path',type=Path)
    p=sub.add_parser('launch',help='Apply policies before launching an agent CLI');p.add_argument('argv',nargs=argparse.REMAINDER)
    args=parser.parse_args()
    try:
        if args.command in (None,'ui'):
            open_manager(['web','--view','harness']);return
        manager=Manager(args.state,args.home)
        if args.command=='serve':
            from .server import run_server
            if args.interval<3:parser.error('Minimum scan interval is 3 seconds')
            run_server(manager,args.port,args.interval,args.open);return
        if args.command=='watch':
            if args.interval<3:parser.error('Minimum scan interval is 3 seconds')
            while True:
                result=manager.reconcile()
                if result['changed'] or result['errors']:print(json.dumps(result),flush=True)
                time.sleep(args.interval)
        elif args.command=='export':result=manager.initialize()
        elif args.command in ['status','scan']:result=manager.snapshot() if args.command=='status' else manager.reconcile(dry_run=True)
        elif args.command=='apply':result=manager.reconcile()
        elif args.command=='restore':result=manager.restore()
        elif args.command in ['pause','resume']:
            policy=manager.initialize();manager.update(policy['revision'],paused=args.command=='pause');result=manager.reconcile()
        elif args.command=='add-project':
            policy=manager.initialize();manager.update(policy['revision'],projects=policy['projects']+[str(args.path.expanduser().resolve())]);result=manager.reconcile()
        elif args.command=='launch':
            argv=args.argv[1:] if args.argv[:1]==['--'] else args.argv
            if not argv:parser.error('Provide an agent command after launch --')
            manager.settle_seconds=0;result=manager.reconcile()
            if result['paused'] or result['errors']:raise ValueError('Cannot launch with paused maintenance or unresolved policy errors. Inspect status first.')
            os.execvp(argv[0],argv)
        else:parser.error('Unknown command')
        if getattr(args,'json',False) or args.command=='export':print(json.dumps(result,indent=2))
        elif args.command=='status':
            print(f"{len(result['skills'])} skills · {sum(not r['explicit'] for r in result['skills'])} implicit allowed · {'paused' if result['policy']['paused'] else 'maintenance enabled'}")
            print(f"{result['pending_files']} pending files · {len(result['errors'])} errors")
            for error in result['errors']:print(error)
            print('Open the checkbox list: harness-config ui')
        else:print(json.dumps(result,indent=2))
        if result.get('errors') or result.get('conflicts'):return 1
    except (ValueError,OSError) as e:
        print(str(e),file=sys.stderr);return 1
    except KeyboardInterrupt:return 0
    return 0

if __name__=='__main__':raise SystemExit(main())
