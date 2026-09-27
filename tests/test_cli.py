"""CLI behavior against a deliberately slow local policy server."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import sys
import threading
import time

from harness_defaults.__main__ import main


def test_ui_waits_for_slow_inventory_response(tmp_path, monkeypatch):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            time.sleep(5.2)
            self.send_response(200)
            self.send_header('Content-Length', '2')
            self.end_headers()
            self.wfile.write(b'{}')

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    state = tmp_path / 'state'
    state.mkdir()
    (state / 'server.json').write_text(json.dumps({'port': server.server_port, 'token': 'fixture-token'}))
    opened = []
    monkeypatch.setattr('webbrowser.open', opened.append)
    monkeypatch.setattr(sys, 'argv', ['harness_defaults', '--state', str(state), 'ui'])
    try:
        assert main() is None
        assert opened == [f'http://127.0.0.1:{server.server_port}/#token=fixture-token']
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)
