"""Policy decisions, safe reconciliation, and conflict-aware restoration."""
from contextlib import contextmanager
from datetime import datetime,timezone
import fcntl
import os
from pathlib import Path
import threading
import time
from .discovery import discover,HOSTS
from .storage import atomic_write,digest,json_read,json_write,read_bytes,render_policy


def now():return datetime.now(timezone.utc).isoformat(timespec='seconds')


class Manager:
    def __init__(self,state,home=None,settle_seconds=3):
        self.state=Path(state).expanduser().resolve();self.home=Path(home or Path.home()).expanduser().resolve()
        self.settle_seconds=settle_seconds;self.mutex=threading.RLock()
        self.state.mkdir(parents=True,exist_ok=True);self.state.chmod(0o700)

    @contextmanager
    def locked(self):
        with self.mutex:
            with open(self.state/'lock','a') as lock:
                os.chmod(self.state/'lock',0o600)
                fcntl.flock(lock,fcntl.LOCK_EX)
                try:yield
                finally:fcntl.flock(lock,fcntl.LOCK_UN)

    def _policy(self):
        policy=json_read(self.state/'policy.json')
        if policy is None:
            policy={'schema':1,'revision':0,'default_explicit':True,'skills':{},'groups':{},'projects':[],'paused':False}
            rows,_,_=discover(self.home,policy)
            policy['skills']={row['id']:False for row in rows if row['system']}
            json_write(self.state/'policy.json',policy)
        self.validate(policy)
        return policy

    @staticmethod
    def validate(policy):
        if not isinstance(policy,dict) or policy.get('schema')!=1:raise ValueError('Unsupported policy schema')
        if type(policy.get('revision')) is not int or policy['revision']<0:raise ValueError('Invalid policy revision')
        if policy.get('default_explicit') is not True:raise ValueError('New skills must default to explicit invocation')
        if type(policy.get('paused')) is not bool:raise ValueError('paused must be a boolean')
        for key in ['skills','groups']:
            if not isinstance(policy.get(key),dict):raise ValueError(f'{key} must be a mapping')
            for name,value in policy[key].items():
                if not isinstance(name,str) or type(value) is not bool:raise ValueError('Policy choices must be booleans')
        if not isinstance(policy.get('projects'),list) or any(not isinstance(p,str) or not Path(p).is_absolute() for p in policy['projects']):raise ValueError('Project roots must be absolute paths')

    def initialize(self):
        with self.locked():return self._policy()

    @staticmethod
    def decision(row,policy):
        if row['id'] in policy['skills']:return policy['skills'][row['id']],'Individual choice'
        if row['group'] in policy['groups']:return policy['groups'][row['group']],'Group default'
        return True,'New-skill default'

    def _inventory(self,policy):
        rows,groups,notices=discover(self.home,policy)
        for row in rows:
            row['explicit'],row['inherited_from']=self.decision(row,policy)
        return rows,groups,notices

    def _operations(self,rows):
        targets={};errors=[]
        for row in rows:
            if row['errors']:
                errors.extend(row['errors']);row['status']='error';continue
            row['status']='current'
            for item in row['files']:
                source=Path(item['path'])
                target=(source.parent/'agents/openai.yaml' if row['host']=='codex' else source).resolve()
                record=targets.setdefault(str(target),{'path':target,'explicit':row['explicit'],'host':row['host'],'rows':[],'sources':[],'conflict':False})
                record['rows'].append(row);record['sources'].append(source)
                if record['explicit']!=row['explicit']:record['conflict']=True
        operations=[]
        for record in targets.values():
            try:
                if record['conflict']:raise ValueError('Shared file has conflicting invocation choices; align the choices for both hosts')
                data=read_bytes(record['path']);result=render_policy(record['host'],data,record['explicit'])
                if result!=data:
                    recent=max([p.stat().st_mtime for p in record['sources']]+([record['path'].stat().st_mtime] if record['path'].exists() else []))
                    status='waiting' if time.time()-recent<self.settle_seconds else 'pending'
                    for row in record['rows']:
                        if row['status']!='error':row['status']=status
                    if status=='pending':operations.append((record,data,result))
            except Exception as e:
                message=f"{record['path']}: {e}";errors.append(message)
                for row in record['rows']:row['status']='error';row['errors'].append(message)
        return operations,errors

    def snapshot(self):
        with self.locked():
            policy=self._policy();rows,groups,notices=self._inventory(policy)
            operations,errors=self._operations(rows)
            return {'policy':policy,'skills':rows,'groups':groups,'notices':notices,'errors':errors,
                    'pending_files':len(operations),'last_run':json_read(self.state/'last-run.json',{}),
                    'hosts':[{'id':h,'present':(self.home/('.'+h)).exists(),'skills':sum(r['host']==h for r in rows)} for h in HOSTS],
                    'state_path':str(self.state),'scanned_at':now()}

    def update(self,revision,skills=None,groups=None,projects=None,paused=None):
        with self.locked():
            policy=self._policy()
            if type(revision) is not int or policy['revision']!=revision:raise ValueError('Policy changed in another window. Reload before saving.')
            rows,available_groups,_=self._inventory(policy)
            for key,patch,allowed in [('skills',skills,{r['id'] for r in rows}),('groups',groups,{g['id'] for g in available_groups})]:
                if patch is None:continue
                if not isinstance(patch,dict):raise ValueError(f'{key} must be a mapping')
                for name,value in patch.items():
                    if name not in allowed and not (value is None and name in policy[key]):raise ValueError('Unknown skill or group. Rescan before saving.')
                    if value is None:policy[key].pop(name,None)
                    elif type(value) is bool:policy[key][name]=value
                    else:raise ValueError('Choices must be booleans or null for inherited values')
            if projects is not None:
                if not isinstance(projects,list) or len(projects)>100 or any(not isinstance(p,str) for p in projects):raise ValueError('Provide at most 100 project paths')
                resolved=[]
                for value in projects:
                    p=Path(value).expanduser()
                    if not p.is_absolute() or not p.is_dir():raise ValueError(f'Project folder does not exist: {value}')
                    if p.resolve() in [self.home,Path('/')]:raise ValueError('Register a project directory, not your entire home or filesystem')
                    resolved.append(str(p.resolve()))
                policy['projects']=list(dict.fromkeys(resolved))
            if paused is not None:
                if type(paused) is not bool:raise ValueError('paused must be a boolean')
                policy['paused']=paused
            self.validate(policy);policy['revision']+=1
            json_write(self.state/'policy.json',policy)
            return policy

    def reconcile(self,dry_run=False):
        with self.locked():
            policy=self._policy();rows,groups,notices=self._inventory(policy)
            operations,errors=self._operations(rows)
            result={'at':now(),'changed':0,'planned':len(operations),'skills':len(rows),'errors':errors,'notices':notices,
                    'paused':policy['paused'],'dry_run':dry_run,'waiting':sum(r['status']=='waiting' for r in rows),'paths':[]}
            if not dry_run and not policy['paused']:
                backups=json_read(self.state/'backups.json',{})
                for record,before,after in operations:
                    target=record['path'];key=str(target)
                    try:
                        # Observe vendor/user changes as a new restore baseline, never revive an old version.
                        prior=backups.get(key)
                        if prior and prior['after']==digest(before):entry=dict(prior)
                        else:
                            entry={'original':digest(before),'original_mode':target.stat().st_mode & 0o777 if target.exists() else None}
                            if before is not None:
                                blob=self.state/'backups'/digest(before)
                                if not blob.exists():atomic_write(blob,before,mode=0o600)
                        entry.update(after=digest(after),at=now())
                        # Write-ahead receipt: a crash before replacement is a safe restore conflict.
                        backups[key]=entry;json_write(self.state/'backups.json',backups)
                        atomic_write(target,after,expected=before)
                        result['changed']+=1;result['paths'].append(key)
                    except Exception as e:result['errors'].append(f'{target}: {e}')
            if not dry_run:json_write(self.state/'last-run.json',result)
            return result

    def restore(self):
        with self.locked():
            policy=self._policy();policy['paused']=True;policy['revision']+=1;json_write(self.state/'policy.json',policy)
            backups=json_read(self.state/'backups.json',{});result={'restored':0,'conflicts':[],'paused':True}
            for key,entry in list(backups.items()):
                path=Path(key)
                try:
                    current=read_bytes(path)
                    if digest(current)!=entry['after']:raise ValueError('Changed outside the manager; left untouched')
                    if entry['original'] is None:
                        if path.is_symlink():raise ValueError('Path became a symbolic link; left untouched')
                        if read_bytes(path)!=current:raise ValueError('Changed during restore')
                        path.unlink()
                    else:
                        original=read_bytes(self.state/'backups'/entry['original'])
                        if original is None or digest(original)!=entry['original']:raise ValueError('Backup is missing or damaged')
                        atomic_write(path,original,expected=current,mode=entry['original_mode'])
                    del backups[key];json_write(self.state/'backups.json',backups);result['restored']+=1
                except Exception as e:result['conflicts'].append(f'{path}: {e}')
            return result
