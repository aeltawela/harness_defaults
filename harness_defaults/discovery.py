"""Read only discovery. Cache presence is never treated as proof of enablement."""
import os
from pathlib import Path
import tomllib
from urllib.parse import quote
from .storage import frontmatter, json_read, read_bytes

HOSTS=('codex','qwen','claude')
SKIP={'.git','node_modules','.venv','vendor','__pycache__','.cursor','.claude','.codex','.qwen'}


def ident(*parts):return '/'.join(quote(str(p),safe='') for p in parts)


def skill_files(root):
    if root.is_file():
        if root.name=='SKILL.md':yield root
        return
    seen=set()
    for folder,dirs,files in os.walk(root,followlinks=True):
        real=Path(folder).resolve()
        if real in seen:dirs[:]=[];continue
        seen.add(real)
        dirs[:]=sorted(d for d in dirs if d not in SKIP and not d.startswith('.'))
        if 'SKILL.md' in files:
            yield Path(folder)/'SKILL.md';dirs[:]=[]


def discover(home,policy):
    home=Path(home);rows={};groups={};notices=[]
    def notice(message):
        if message not in notices:notices.append(message)
    def group(host,key,label,source,capabilities=None):
        gid=ident(host,key)
        groups.setdefault(gid,dict(id=gid,host=host,label=label,source=source,capabilities=capabilities or []))
        return gid
    def add(host,gid,key,path,version=None,system=False,command=False):
        sid=ident(host,gid,key)
        row=rows.setdefault(sid,dict(id=sid,host=host,group=gid,name=path.stem if command else path.parent.name,
            description='',files=[],warnings=[],system=system,errors=[]))
        raw_path=str(path.absolute())
        if any(x['path']==raw_path for x in row['files']):return
        row['files'].append({'path':raw_path,'version':version})
        try:
            data=read_bytes(path)
            meta,body,_=frontmatter(data,allow_missing=host=='claude')
            row['name']=str(meta.get('name') or row['name'])
            row['description']=str(meta.get('description') or '')[:2000]
            if meta.get('user-invocable') is False:
                row['warnings'].append('user-invocable is false: explicit slash invocation remains hidden by the author.')
            if meta.get('hooks'):row['warnings'].append('This skill also declares hooks; the invocation flag is not a general hook permission.')
        except Exception as e:row['errors'].append(f'{path}: {e}')
    def add_root(host,root,key,label,source,system=False):
        gid=group(host,key,label,source)
        for p in skill_files(root):add(host,gid,str(p.relative_to(root)),p,system=system)
        return gid
    def package(host,root,market,name,version=None):
        manifest_path=root/('.codex-plugin/plugin.json' if host=='codex' else '.claude-plugin/plugin.json' if host=='claude' else 'qwen-extension.json')
        try: manifest=json_read(manifest_path,{})
        except Exception as e:notice(f'{manifest_path}: {e}');return
        if not isinstance(manifest,dict):notice(f'Invalid plugin manifest: {manifest_path}');return
        capabilities=[]
        for key,label in [('mcpServers','MCP tools'),('mcp_servers','MCP tools'),('hooks','Lifecycle hooks'),('contextFileName','Extension instructions'),('agents','Agents')]:
            if manifest.get(key):capabilities.append(label)
        for path,label in [('.mcp.json','MCP tools'),('hooks/hooks.json','Hook files'),('GEMINI.md','Extension instructions'),('QWEN.md','Extension instructions'),('CLAUDE.md','Plugin instructions')]:
            if (root/path).exists() and label not in capabilities:capabilities.append(label)
        gid=group(host,'plugin:'+market+':'+name,name, 'Plugin cache • availability controlled by host' if host!='qwen' else 'Installed extension',capabilities)
        declared=manifest.get('skills','skills')
        if isinstance(declared,str):declared=[declared]
        if not isinstance(declared,list):notice(f'Unsupported skills declaration in {manifest_path}');return
        # Claude's declared paths supplement the default skills directory.
        if host=='claude' and 'skills' not in declared:declared=['skills']+declared
        for entry in declared:
            if not isinstance(entry,str):notice(f'Unsupported skill path in {manifest_path}');continue
            target=root/entry
            try:target.resolve().relative_to(root.resolve())
            except ValueError:notice(f'Skipped skill root outside package: {target}');continue
            for p in skill_files(target):add(host,gid,str(p.relative_to(root)),p,version)
        if host=='claude':
            if 'skills' not in manifest and not (root/'skills').exists() and (root/'SKILL.md').is_file():
                add(host,gid,'SKILL.md',root/'SKILL.md',version)
            command_roots=manifest.get('commands',['commands'])
            if isinstance(command_roots,str):command_roots=[command_roots]
            if not isinstance(command_roots,list):notice(f'Unsupported commands declaration in {manifest_path}');command_roots=[]
            for entry in command_roots:
                if not isinstance(entry,str):notice(f'Unsupported command path in {manifest_path}');continue
                commands=root/entry
                try:commands.resolve().relative_to(root.resolve())
                except ValueError:notice(f'Skipped command root outside package: {commands}');continue
                files=[commands] if commands.is_file() and commands.suffix=='.md' else (commands.rglob('*.md') if commands.is_dir() else [])
                for p in files:add(host,gid,str(p.relative_to(root)),p,version,command=True)
    for host in HOSTS:
        base=home/('.'+host)
        add_root(host,base/'skills','personal','Personal skills','User directory')
        if host=='codex':
            add_root(host,base/'skills/.system','system','Built-in system skills','Codex system directory',True)
            add_root(host,home/'.agents/skills','shared','Shared agent skills','User directory')
        if host=='claude':
            gid=group(host,'commands','Personal commands','Legacy slash commands')
            for p in (base/'commands').rglob('*.md') if (base/'commands').exists() else []:
                add(host,gid,str(p.relative_to(base/'commands')),p,command=True)
        if host in ('codex','claude'):
            cache=base/'plugins/cache'
            for market in sorted(cache.iterdir()) if cache.exists() else []:
                if not market.is_dir():continue
                for plugin in sorted(market.iterdir()):
                    if not plugin.is_dir():continue
                    for version in sorted(plugin.iterdir()):
                        if version.is_dir():package(host,version,market.name,plugin.name,version.name)
        else:
            extensions=base/'extensions'
            for ext in sorted(extensions.iterdir()) if extensions.exists() else []:
                if ext.is_dir() and (ext/'qwen-extension.json').exists():package(host,ext,'extensions',ext.name)
            try:
                settings=json_read(base/'settings.json',{})
                for item in settings.get('skills',{}).get('directories',[]):
                    root=Path(item).expanduser()
                    if not root.is_absolute():notice(f'Qwen relative skill directory needs a registered project: {item}');continue
                    add_root(host,root,'extra:'+str(root),'Extra skills: '+root.name,'Configured Qwen directory')
            except Exception as e:notice(f'Could not read Qwen skill directories: {e}')
    for project in policy.get('projects',[]):
        root=Path(project)
        if not root.is_dir():notice(f'Project root unavailable: {root}');continue
        # Only explicitly registered project roots, not arbitrary home-wide recursive scans.
        for host in HOSTS:
            for sub in (['.agents/skills','.codex/skills'] if host=='codex' else ['.'+host+'/skills']):
                add_root(host,root/sub,'project:'+str(root)+':'+sub,root.name+' / '+sub,'Registered project')
            if host=='claude':
                commands=root/'.claude/commands';gid=group(host,'project-commands:'+str(root),root.name+' / commands','Registered project')
                for p in commands.rglob('*.md') if commands.exists() else []:add(host,gid,str(p.relative_to(commands)),p,command=True)
    try:
        config=home/'.codex/config.toml'
        if config.exists():
            c=tomllib.loads(config.read_text());disabled={str(Path(x['path']).expanduser().resolve()) for x in c.get('skills',{}).get('config',[]) if x.get('enabled') is False and 'path' in x}
            for row in rows.values():
                if any(str(Path(f['path']).resolve()) in disabled for f in row['files']):row['warnings'].append('Disabled in Codex configuration; this manager does not enable it.')
    except Exception as e:notice(f'Could not read Codex skill enablement: {e}')
    return sorted(rows.values(),key=lambda r:(r['host'],r['group'],r['name'].casefold())),list(groups.values()),notices
