#!/usr/bin/env python3
"""Localhost-only web server for the Unified Math Learning Cockpit."""
from __future__ import annotations

import argparse
import json
import mimetypes
import socket
import sys
import urllib.parse
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import cockpit_engine as engine

STATIC = Path(__file__).resolve().parent / "cockpit" / "static"


class Handler(BaseHTTPRequestHandler):
    server_version = "LearningCockpit/1.0"

    def log_message(self, fmt, *args):
        if getattr(self.server, "quiet", False):
            return
        super().log_message(fmt, *args)

    def json_response(self, value, status=HTTPStatus.OK):
        body = json.dumps(value, ensure_ascii=False, default=list).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def error_json(self, exc):
        status = HTTPStatus.BAD_REQUEST if isinstance(exc, (ValueError, KeyError, PermissionError)) else HTTPStatus.INTERNAL_SERVER_ERROR
        self.json_response({"error": str(exc)}, status)

    def parsed(self):
        return urllib.parse.urlparse(self.path)

    def query(self):
        return {k: v[-1] for k, v in urllib.parse.parse_qs(self.parsed().query).items()}

    def read_body(self):
        length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(length).decode("utf-8")) if length else {}

    def serve_file(self, path: Path):
        if not path.exists() or not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mimetypes.guess_type(path.name)[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "private, max-age=300")
        self.end_headers()
        self.wfile.write(content)

    def do_GET(self):
        try:
            route = self.parsed().path
            q = self.query()
            if route == "/api/bootstrap":
                state = engine.load_state()
                self.json_response({"today": engine.today_plan(), "settings": state["settings"],
                                    "catalog": engine.catalog_summary(),
                                    "error_types": sorted(engine.ERROR_TYPES)})
            elif route == "/api/today":
                self.json_response(engine.today_plan())
            elif route == "/api/nodes":
                self.json_response(engine.list_nodes(q.get("q", ""), q.get("layer", ""), q.get("course", ""))[:500])
            elif route == "/api/question":
                item = engine.get_question(q["id"]) if q.get("id") else engine.next_question(
                    q.get("course", ""), int(q["node"]) if q.get("node") else None)
                self.json_response(item or {}, HTTPStatus.OK if item else HTTPStatus.NOT_FOUND)
            elif route == "/api/session":
                self.json_response(engine.load_state().get("active_session") or {})
            elif route == "/media":
                self.serve_file(engine.resolve_media(q.get("path", "")))
            elif route == "/health":
                self.json_response({"ok": True, "vault": str(engine.VAULT)})
            else:
                relative = "index.html" if route in ("/", "") else route.lstrip("/")
                candidate = (STATIC / relative).resolve()
                if STATIC.resolve() not in candidate.parents and candidate != STATIC.resolve():
                    raise PermissionError("invalid static path")
                self.serve_file(candidate)
        except Exception as exc:
            self.error_json(exc)

    def do_POST(self):
        try:
            route = self.parsed().path
            body = self.read_body()
            if route == "/api/attempt":
                result = engine.record_attempt(body)
            elif route == "/api/review":
                result = engine.grade_review(body["key"], int(body["rating"]), body.get("session_id"))
            elif route == "/api/subskill":
                result = engine.complete_subskill(int(body["node"]), body["subskill"], bool(body["done"]))
            elif route == "/api/session/start":
                result = engine.start_session(body.get("kind", "guided"), body.get("course", ""), int(body.get("minutes", 150)))
            elif route == "/api/session/finish":
                result = engine.finish_session()
            elif route == "/api/remediation/start":
                result = engine.start_remediation(int(body["target"]))
            elif route == "/api/remediation/retest":
                result = engine.resume_remediation()
            elif route == "/api/settings":
                result = engine.update_settings(body)
            else:
                self.json_response({"error": "not found"}, HTTPStatus.NOT_FOUND)
                return
            self.json_response(result)
        except Exception as exc:
            self.error_json(exc)


def port_open(host: str, port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.25)
        return sock.connect_ex((host, port)) == 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()
    host = "127.0.0.1"
    url = f"http://{host}:{args.port}/"
    if port_open(host, args.port):
        if not args.no_browser:
            webbrowser.open(url)
        print(f"Cockpit already running at {url}")
        return
    server = ThreadingHTTPServer((host, args.port), Handler)
    server.quiet = args.quiet
    print(f"Unified Math Learning Cockpit: {url}")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    main()
