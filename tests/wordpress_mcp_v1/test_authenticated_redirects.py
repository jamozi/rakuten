from __future__ import annotations

import base64
from collections.abc import Iterator
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
from pathlib import Path
import sys
from threading import Thread
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _load(name: str, relative_path: str) -> Any:
    specification = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


publication = _load(
    "wordpress_publication_request_redirect_test",
    "scripts/raos_wordpress_publication_request.py",
)
operator = _load(
    "wordpress_deployment_operator_redirect_test",
    "scripts/raos_wordpress_deployment_operator.py",
)


@contextmanager
def _serve(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    server.daemon_threads = True
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _destination_handler(
    requests: list[dict[str, str | None]],
) -> type[BaseHTTPRequestHandler]:
    class DestinationHandler(BaseHTTPRequestHandler):
        def _record(self) -> None:
            requests.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                }
            )
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

        do_GET = _record
        do_POST = _record

        def log_message(self, *_: object) -> None:
            return

    return DestinationHandler


def _redirect_handler(
    location: str, requests: list[dict[str, str | None]]
) -> type[BaseHTTPRequestHandler]:
    class RedirectHandler(BaseHTTPRequestHandler):
        def _redirect(self) -> None:
            length = int(self.headers.get("Content-Length", "0"))
            if length:
                self.rfile.read(length)
            requests.append(
                {
                    "method": self.command,
                    "path": self.path,
                    "authorization": self.headers.get("Authorization"),
                }
            )
            self.send_response(302)
            self.send_header("Location", location)
            self.send_header("Content-Length", "0")
            self.end_headers()

        do_GET = _redirect
        do_POST = _redirect

        def log_message(self, *_: object) -> None:
            return

    return RedirectHandler


def test_editor_mcp_refuses_cross_origin_redirect_before_authorized_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin_requests: list[dict[str, str | None]] = []
    destination_requests: list[dict[str, str | None]] = []
    with _serve(_destination_handler(destination_requests)) as destination:
        with _serve(
            _redirect_handler(f"{destination}/capture", origin_requests)
        ) as origin:
            endpoint = f"{origin}/editor"
            monkeypatch.setattr(publication, "EDITOR_ENDPOINT", endpoint)
            client = object.__new__(publication.EditorMcpClient)
            client.endpoint = endpoint
            client.username = "redirect-test-editor"
            client.password = "not-a-production-password-1234"
            client.session_id = None
            client.next_id = 1

            with pytest.raises(
                publication.PublicationFailure,
                match="^RAOS_WORDPRESS_REQUEST_REDIRECT_REFUSED$",
            ):
                client._request({"jsonrpc": "2.0", "id": 1, "method": "ping"})

    expected = "Basic " + base64.b64encode(
        b"redirect-test-editor:not-a-production-password-1234"
    ).decode("ascii")
    assert origin_requests == [
        {"method": "POST", "path": "/editor", "authorization": expected}
    ]
    assert destination_requests == []


def test_deployment_client_refuses_cross_origin_redirect_before_authorized_second_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin_requests: list[dict[str, str | None]] = []
    destination_requests: list[dict[str, str | None]] = []
    with _serve(_destination_handler(destination_requests)) as destination:
        with _serve(
            _redirect_handler(f"{destination}/capture", origin_requests)
        ) as origin:
            monkeypatch.setattr(operator, "DEPLOY_API", f"{origin}/deploy")
            monkeypatch.setattr(
                operator,
                "credentials",
                lambda: ("redirect-test-deployment", "not-a-production-password-5678"),
            )

            with pytest.raises(
                operator.OperatorFailure,
                match="^WORDPRESS_MCP_REDIRECT_REFUSED$",
            ):
                operator.request_json("GET", "/status")

    expected = "Basic " + base64.b64encode(
        b"redirect-test-deployment:not-a-production-password-5678"
    ).decode("ascii")
    assert origin_requests == [
        {"method": "GET", "path": "/deploy/status", "authorization": expected}
    ]
    assert destination_requests == []
