import json
import threading
import urllib.request
import urllib.error
import pytest
from harness_defaults.engine import Manager
from harness_defaults.server import create_server

@pytest.fixture
def service(tmp_path):
    m=Manager(tmp_path/'state',tmp_path/'home',settle_seconds=0)
    p=m.home/'.claude/skills/sample/SKILL.md';p.parent.mkdir(parents=True);p.write_text('---\nname: sample\n---\nBody\n')
    server=create_server(m,0,'test-secret');thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    yield server,m
    server.shutdown();server.server_close();thread.join()


def request(server,path='/api/state',token='test-secret',origin=None,body=None,host=None):
    base='http://127.0.0.1:'+str(server.server_port)
    headers={'Authorization':'Bearer '+token}
    if origin is not None:headers['Origin']=origin
    if host is not None:headers['Host']=host
    if body is not None:headers['Content-Type']='application/json'
    req=urllib.request.Request(base+path,headers=headers,data=json.dumps(body).encode() if body is not None else None)
    return urllib.request.urlopen(req)


def test_auth_and_origin_guards(service):
    server,m=service
    for kwargs in [{'token':'wrong'},{'origin':'https://evil.invalid'},{'host':'evil.invalid'}]:
        with pytest.raises(urllib.error.HTTPError) as e:request(server,**kwargs)
        assert e.value.code==403
    assert json.load(request(server))['skills'][0]['name']=='sample'


def test_save_updates_actual_metadata_and_stale_save_rejected(service):
    server,m=service
    s=json.load(request(server));sid=s['skills'][0]['id']
    response=json.load(request(server,'/api/save',body={'revision':0,'skills':{sid:False}}))
    assert response['state']['skills'][0]['explicit'] is False
    assert b'disable-model-invocation: false' in (m.home/'.claude/skills/sample/SKILL.md').read_bytes()
    with pytest.raises(urllib.error.HTTPError) as e:request(server,'/api/save',body={'revision':0,'skills':{sid:True}})
    assert e.value.code==409


def test_root_has_security_headers_and_unknown_routes_404(service):
    server,m=service
    response=request(server,'/')
    assert response.headers['Content-Security-Policy'] and response.headers['Cache-Control']=='no-store'
    assert b'harness_defaults' in response.read()
    with pytest.raises(urllib.error.HTTPError) as e:request(server,'/../../etc/passwd')
    assert e.value.code==404
