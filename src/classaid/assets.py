# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" Locating the Vite-built frontend assets (frontend/ -> src/classaid/static/dist/).

In production, entry files are resolved through Vite's manifest (hashed file names).
With CLASSAID_VITE_DEV_SERVER set (e.g. http://localhost:5173), modules are loaded from
the Vite dev server instead ("backend integration": pages and API stay on Flask's origin).
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import msgspec
from flask import current_app, url_for

MANIFEST = Path(__file__).resolve().parent / 'static' / 'dist' / '.vite' / 'manifest.json'


class AssetsNotBuiltError(RuntimeError):
    def __init__(self) -> None:
        super().__init__("Frontend assets are not built.  Run `pnpm --dir frontend install && pnpm --dir frontend build`.")


@dataclass
class EntryAssets:
    scripts: list[str] = field(default_factory=list)
    styles: list[str] = field(default_factory=list)


def _manifest() -> dict[str, Any]:
    if not MANIFEST.exists():
        raise AssetsNotBuiltError
    data: dict[str, Any] = msgspec.json.decode(MANIFEST.read_bytes())
    return data


def entry_assets(name: str) -> EntryAssets:
    """ Script and stylesheet URLs for the frontend entry `name` (frontend/src/<name>/main.ts). """
    source = f'src/{name}/main.ts'
    dev_server = os.environ.get('CLASSAID_VITE_DEV_SERVER') or current_app.config.get('CLASSAID_VITE_DEV_SERVER')
    if dev_server:
        base = f"{dev_server.rstrip('/')}/static/dist"
        return EntryAssets(scripts=[f'{base}/@vite/client', f'{base}/{source}'])

    manifest = _manifest()
    assets = EntryAssets(scripts=[url_for('static', filename=f"dist/{manifest[source]['file']}")])
    seen: set[str] = set()

    def collect_css(key: str) -> None:
        if key in seen:
            return
        seen.add(key)
        chunk = manifest[key]
        assets.styles.extend(url_for('static', filename=f'dist/{css}') for css in chunk.get('css', []))
        for imported in chunk.get('imports', []):
            collect_css(imported)

    collect_css(source)
    return assets
