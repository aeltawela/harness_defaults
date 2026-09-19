"""Loopback-only API. No arbitrary file operations and no unauthenticated data APIs."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import hmac
import json
from pathlib import Path
import secrets
import threading
from .storage import json_write


def create_server(manager,port,token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def respond(self,status,value,html=False):
            data=value.encode() if html else json.dumps(value,ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header('Content-Type','text/html; charset=utf-8' if html else 'application/json')
            self.send_header('Content-Length',str(len(data)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',f"default-src 'none'; script-src 'nonce-{self.nonce}'; style-src 'unsafe-inline'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
            self.end_headers();self.wfile.write(data)
        def guard(self,auth=True):
            self.nonce=secrets.token_urlsafe(20)
            authority='127.0.0.1:'+str(self.server.server_port)
            if self.headers.get('Host')!=authority or self.headers.get('Origin') not in (None,'http://'+authority):
                self.respond(403,{'error':'Only the local manager page can make this request.'});return False
            if auth and not hmac.compare_digest(self.headers.get('Authorization',''),'Bearer '+token):
                self.respond(403,{'error':'Open the manager using harness_defaults ui to authenticate.'});return False
            return True
        def do_GET(self):
            if not self.guard(auth=self.path!='/'):return
            if self.path=='/':
                self.respond(200,Path(__file__).with_name('ui.html').read_text().replace('__NONCE__',self.nonce),html=True)
            elif self.path=='/api/state':
                try:self.respond(200,manager.snapshot())
                except Exception as e:self.respond(500,{'error':str(e)})
            else:self.respond(404,{'error':'Not found'})
        def do_POST(self):
            if not self.guard():return
            try:
                if self.headers.get('Content-Type')!='application/json':raise ValueError('Expected application/json')
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=1024*1024:raise ValueError('Invalid request size')
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('Expected a JSON object')
                if self.path=='/api/save':
                    if set(data)-{'revision','skills','groups','projects','paused'}:raise ValueError('Unknown policy fields')
                    manager.update(**data);result=manager.reconcile()
                elif self.path=='/api/scan':result=manager.reconcile()
                elif self.path=='/api/restore':result=manager.restore()
                else:self.respond(404,{'error':'Not found'});return
                self.respond(200,{'result':result,'state':manager.snapshot()})
            except ValueError as e:self.respond(409 if 'changed in another window' in str(e) else 400,{'error':str(e)})
            except Exception as e:self.respond(500,{'error':str(e)})
    server=ThreadingHTTPServer(('127.0.0.1',port),Handler)
    server.daemon_threads=True
    return server


def run_server(manager,port=47831,interval=15,open_browser=False):
    import webbrowser
    token=secrets.token_urlsafe(32)
    server=create_server(manager,port,token)
    json_write(manager.state/'server.json',{'port':server.server_port,'token':token})
    stop=threading.Event()
    def worker():
        while not stop.is_set():
            try:manager.reconcile()
            except Exception as e:json_write(manager.state/'last-run.json',{'errors':[str(e)],'changed':0})
            stop.wait(interval)
    thread=threading.Thread(target=worker,daemon=True);thread.start()
    if open_browser:webbrowser.open(f'http://127.0.0.1:{server.server_port}/#token={token}')
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:stop.set();server.server_close();thread.join(timeout=5)
