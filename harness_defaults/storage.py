"""Strict policy storage, round-trip YAML, and crash-resistant file replacement."""
import hashlib
import io
import json
import os
from pathlib import Path
import re
import tempfile
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

MAX_FILE = 2 * 1024 * 1024

def read_bytes(path):
    if not path.exists():
        return None
    if not path.is_file() or path.stat().st_size > MAX_FILE:
        raise ValueError(f'Not a regular file or exceeds 2 MiB: {path}')
    return path.read_bytes()


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def atomic_write(path, data, expected=Ellipsis, mode=None):
    path=Path(path)
    resolved=path.resolve()
    if expected is not Ellipsis and read_bytes(resolved)!=expected:
        raise ValueError(f'File changed during sync: {path}')
    resolved.parent.mkdir(parents=True,exist_ok=True)
    permissions=mode if mode is not None else (resolved.stat().st_mode & 0o777 if resolved.exists() else 0o600)
    fd,temp=tempfile.mkstemp(prefix='.invocation-',dir=resolved.parent)
    try:
        os.fchmod(fd,permissions)
        with os.fdopen(fd,'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        if path.resolve()!=resolved or (expected is not Ellipsis and read_bytes(resolved)!=expected):
            raise ValueError(f'File changed during sync: {path}')
        os.replace(temp,resolved)
    finally:
        if os.path.exists(temp):os.unlink(temp)


def json_write(path,value):
    atomic_write(path,(json.dumps(value,indent=2,ensure_ascii=False)+'\n').encode(),mode=0o600)


def json_read(path,default=None):
    raw=read_bytes(Path(path))
    return json.loads(raw) if raw is not None else default


def yaml_parser(newline='\n'):
    y=YAML(typ='rt');y.preserve_quotes=True;y.allow_duplicate_keys=False;y.width=4096;y.line_break=newline
    return y


def mapping(text):
    value=yaml_parser().load(text)
    if value is None:return CommentedMap()
    if not isinstance(value,dict):raise ValueError('YAML must be a mapping')
    return value


def frontmatter(data,allow_missing=False):
    text=data.decode('utf-8')
    match=re.match(r'\A---[ \t]*\r?\n(.*?)^---[ \t]*(?:\r?\n|\Z)',text,re.M|re.S)
    if not match:
        if text.startswith('---') or not allow_missing:raise ValueError('Missing or unterminated YAML frontmatter')
        return CommentedMap(),text,'\n'
    return mapping(match.group(1)),text[match.end():], '\r\n' if '\r\n' in match.group(0) else '\n'


def dump_yaml(value,newline='\n'):
    out=io.StringIO();yaml_parser(newline).dump(value,out);return out.getvalue()


def render_policy(host,data,explicit):
    if host=='codex':
        meta=mapping(data.decode('utf-8')) if data else CommentedMap()
        policy=meta.get('policy')
        if policy is None:policy=CommentedMap();meta['policy']=policy
        if not isinstance(policy,dict):raise ValueError('policy must be a YAML mapping')
        current=policy.get('allow_implicit_invocation')
        if current is not None and type(current) is not bool:raise ValueError('allow_implicit_invocation must be a boolean')
        if current is (not explicit):return data
        policy['allow_implicit_invocation']=not explicit
        return dump_yaml(meta,'\r\n' if data and b'\r\n' in data else '\n').encode()
    meta,body,newline=frontmatter(data,allow_missing=(host=='claude'))
    current=meta.get('disable-model-invocation')
    if current is not None and type(current) is not bool:raise ValueError('disable-model-invocation must be a boolean')
    if current is explicit:return data
    meta['disable-model-invocation']=explicit
    return ('---'+newline+dump_yaml(meta,newline)+'---'+newline+body).encode()
