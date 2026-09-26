"""Shared pytest fixtures.

Provides a temporary application context, a local mock proxy + origin server
(so validation/monitoring can be tested without any live external service), and
sample-data helpers. Qt runs offscreen for headless CI.
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import threading
import urllib.request
from dataclasses import dataclass

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture()
def data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("PROXYATLAS_DATA_DIR", str(tmp_path))
    # Reset the module-level paths singleton to the temp dir.
    import importlib

    import app.core.paths as paths_mod

    importlib.reload(paths_mod)
    return tmp_path


@pytest.fixture()
def ctx(data_dir):
    from app.core.paths import AppPaths
    from app.services.bootstrap import bootstrap

    return bootstrap(AppPaths(data_dir))


class _Origin(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401
        pass

    def do_GET(self):  # noqa: N802
        if self.path.endswith("/ip"):
            body = b'{"ip": "203.0.113.77"}'
        else:
            payload = {"headers": {k: v for k, v in self.headers.items()}, "origin": "203.0.113.77"}
            body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class _Proxy(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):  # noqa: D401
        pass

    def do_GET(self):  # noqa: N802
        try:
            req = urllib.request.Request(self.path)
            req.add_header("Via", "1.1 proxyatlas-test")
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = resp.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:  # noqa: BLE001
            self.send_response(502)
            self.end_headers()


def _serve(handler) -> int:
    server = socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server.server_address[1]


@dataclass
class MockNet:
    proxy_port: int
    origin_port: int

    @property
    def ip_endpoint(self) -> str:
        return f"http://127.0.0.1:{self.origin_port}/ip"

    @property
    def judge_endpoint(self) -> str:
        return f"http://127.0.0.1:{self.origin_port}/get"


@pytest.fixture()
def mock_net() -> MockNet:
    return MockNet(proxy_port=_serve(_Proxy), origin_port=_serve(_Origin))
