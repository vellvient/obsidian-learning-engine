#!/usr/bin/env python3
"""Install or refresh the shared Learning Cockpit in another vault.

Subject behavior belongs in the destination's config/course_catalog.json and
vault_config.json. This installer deliberately does not overwrite either file,
personal state, question banks, notes, or SRS data.
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "vault"
FILES = [
    "cockpit_engine.py",
    "cockpit_app.py",
    "cockpit/static/index.html",
    "cockpit/static/app.js",
    "cockpit/static/styles.css",
    "cockpit/static/cockpit-extra.css",
    "tests/test_cockpit_engine.py",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--vault", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--launch-name", default="Launch Learning Cockpit.bat")
    args = parser.parse_args()
    vault = args.vault.resolve()
    if not (vault / "srs_fsrs.py").exists():
        raise SystemExit(f"Not a learning-engine vault (missing srs_fsrs.py): {vault}")
    if not (vault / "config" / "course_catalog.json").exists():
        raise SystemExit("Create config/course_catalog.json before installing the cockpit.")
    for relative in FILES:
        source = TEMPLATE / relative
        destination = vault / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    launch = vault / args.launch_name
    launch.write_text(
        f"@echo off\ncd /d \"{vault}\"\npython cockpit_app.py --port {args.port}\n",
        encoding="utf-8",
    )
    print(f"Installed shared cockpit in {vault}")
    print("Preserved course config, graph, questions, notes, FSRS, and personal state.")


if __name__ == "__main__":
    main()
