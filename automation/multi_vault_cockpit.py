#!/usr/bin/env python3
"""Launch several independent Learning Cockpits behind one local tabbed page."""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def port_open(port: int) -> bool:
    with socket.socket() as sock:
        sock.settimeout(0.25)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def page(subjects: list[dict]) -> bytes:
    payload = json.dumps([
        {"id": str(row["id"]), "label": str(row.get("label", row["id"])),
         "url": f"http://127.0.0.1:{int(row['port'])}/"}
        for row in subjects
    ], ensure_ascii=False).replace("</", "<\\/")
    return f'''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>A-Level Learning Cockpit</title><style>
*{{box-sizing:border-box}}html,body{{height:100%;margin:0;font:15px system-ui;background:#10151c;color:#eaf0f7}}
header{{height:58px;display:flex;align-items:center;gap:14px;padding:8px 16px;background:#171e28;border-bottom:1px solid #314052}}
h1{{font-size:17px;margin:0 12px 0 0}}button{{border:1px solid #40536a;background:#202b38;color:#dbe7f4;border-radius:8px;padding:9px 15px;cursor:pointer}}
button.active{{background:#2d6cdf;border-color:#6ea1ff;color:white}}iframe{{width:100%;height:calc(100% - 58px);border:0;background:white}}
.status{{margin-left:auto;color:#9fb0c4;font-size:13px}}
</style></head><body><header><h1>A-Level Learning Cockpit</h1><div id="tabs"></div><span class="status">Independent graphs · shared launcher</span></header><iframe id="frame" title="Subject cockpit"></iframe>
<script>const subjects={payload};const tabs=document.querySelector('#tabs'),frame=document.querySelector('#frame');
function openSubject(row){{frame.src=row.url;[...tabs.children].forEach(b=>b.classList.toggle('active',b.dataset.id===row.id));localStorage.setItem('subject',row.id)}}
subjects.forEach(row=>{{const b=document.createElement('button');b.textContent=row.label;b.dataset.id=row.id;b.onclick=()=>openSubject(row);tabs.appendChild(b)}});
openSubject(subjects.find(x=>x.id===localStorage.getItem('subject'))||subjects[0]);</script></body></html>'''.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    subjects: list[dict] = []
    def log_message(self, *_args):
        return
    def do_GET(self):
        route = urllib.parse.urlparse(self.path).path
        if route == "/health":
            body = json.dumps({"ok": True, "subjects": [x["id"] for x in self.subjects]}).encode()
            content_type = "application/json"
        else:
            body = page(self.subjects)
            content_type = "text/html; charset=utf-8"
        self.send_response(200); self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body))); self.send_header("Cache-Control", "no-store")
        self.end_headers(); self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8764)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    config = json.loads(args.config.read_text(encoding="utf-8"))
    subjects = config.get("subjects", [])
    if not subjects:
        raise SystemExit("The launcher config has no subjects.")
    url = f"http://127.0.0.1:{args.port}/"
    if port_open(args.port):
        if not args.no_browser: webbrowser.open(url)
        print(f"A-Level cockpit already running at {url}")
        return
    children = []
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) if sys.platform == "win32" else 0
    for row in subjects:
        port = int(row["port"]); vault = Path(row["vault"]).resolve()
        if port_open(port):
            continue
        child = subprocess.Popen(
            [sys.executable, str(vault / "cockpit_app.py"), "--port", str(port), "--no-browser", "--quiet"],
            cwd=vault, creationflags=creationflags,
        )
        children.append(child)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline and not all(port_open(int(row["port"])) for row in subjects):
        time.sleep(0.15)
    unavailable = [row["label"] for row in subjects if not port_open(int(row["port"]))]
    if unavailable:
        for child in children: child.terminate()
        raise SystemExit("Failed to start: " + ", ".join(unavailable))
    Handler.subjects = subjects
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"A-Level Learning Cockpit: {url}")
    if not args.no_browser: webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        for child in children:
            child.terminate()


if __name__ == "__main__":
    main()
