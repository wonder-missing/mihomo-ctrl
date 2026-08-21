#!/usr/bin/env python3
"""VHS 录制用的假 Mihomo External Controller。"""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import unquote, urlparse

DEFAULT_PORT = 18765


def _leaf(name: str, delay: int | None = None) -> dict[str, Any]:
    history = [{"delay": delay}] if delay is not None else []
    return {"name": name, "type": "Shadowsocks", "udp": True, "history": history}


def _group(
    name: str,
    proxy_type: str,
    now: str,
    nodes: list[str],
    fixed: str | None = None,
) -> dict[str, Any]:
    info: dict[str, Any] = {"name": name, "type": proxy_type, "now": now, "all": nodes}
    if fixed:
        info["fixed"] = fixed
    return info


def initial_proxies() -> dict[str, Any]:
    return {
        "DIRECT": {"name": "DIRECT", "type": "Direct", "udp": True, "history": []},
        "默认": _group("默认", "Selector", "自动选择", ["自动选择", "香港", "美国"]),
        "自动选择": _group(
            "自动选择", "URLTest", "HK-02", ["HK-02"], fixed="HK-02"
        ),
        "香港": _group("香港", "Selector", "HK-02", ["HK-02"]),
        "美国": _group("美国", "Selector", "US-01", ["US-02", "US-01", "US-03"]),
        "HK-02": _leaf("HK-02", 41),
        "US-01": _leaf("US-01", 67),
        "US-02": _leaf("US-02", 28),
        "US-03": _leaf("US-03", 142),
    }


class FixtureState:
    def __init__(self) -> None:
        self.proxies = initial_proxies()

    def snapshot(self) -> dict[str, Any]:
        return {"proxies": self.proxies}

    def switch(self, group: str, node: str) -> None:
        info = self.proxies.get(group)
        if not isinstance(info, dict) or "all" not in info:
            raise KeyError(group)
        nodes = info.get("all", [])
        if node not in nodes:
            raise ValueError(node)
        info["now"] = node


class Handler(BaseHTTPRequestHandler):
    state: FixtureState

    def log_message(self, format: str, *args: object) -> None:
        return

    def _send(self, code: int, payload: dict[str, Any] | None = None) -> None:
        body = b"" if payload is None else json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if body:
            self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/proxies":
            self._send(200, self.state.snapshot())
            return
        if path == "/providers/proxies":
            self._send(200, {"providers": {}})
            return
        self._send(404, {"message": "not found"})

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        prefix = "/proxies/"
        if not path.startswith(prefix) or path == prefix:
            self._send(404, {"message": "not found"})
            return
        group = unquote(path[len(prefix) :])
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode())
        except (ValueError, UnicodeError):
            self._send(400, {"message": "invalid json"})
            return
        node = data.get("name") if isinstance(data, dict) else None
        if not isinstance(node, str):
            self._send(400, {"message": "missing name"})
            return
        try:
            self.state.switch(group, node)
        except KeyError:
            self._send(404, {"message": f"Proxy Group not found: {group}"})
            return
        except ValueError:
            self._send(400, {"message": f"invalid node: {node}"})
            return
        self._send(204)

    def do_DELETE(self) -> None:
        self._send(204)


def serve(port: int) -> None:
    Handler.state = FixtureState()
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"demo fixture on http://127.0.0.1:{port}", flush=True)
    httpd.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    serve(args.port)


if __name__ == "__main__":
    main()
