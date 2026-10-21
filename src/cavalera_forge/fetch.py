# -*- coding: utf-8 -*-
"""Local mode: download the published databases instead of building them.

The hosted instance publishes the exact files it serves
(https://forge.cavalera.news/data/craft.db and market.db). A local server
keeps a copy in its cache directory and refreshes it once a day, so it
needs neither the build pipeline nor the hosted MCP endpoint.
"""
from __future__ import annotations

import logging
import os
import sqlite3
import tempfile
import time
import urllib.request

from . import __version__

DATA_URL = os.environ.get("FORGE_DATA_URL", "https://forge.cavalera.news/data")
FILES = ("craft.db", "market.db")
TTL = 86400

log = logging.getLogger(__name__)


def _valid(path):
    try:
        cx = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
        try:
            return cx.execute("SELECT COUNT(*) FROM meta").fetchone()[0] > 0
        finally:
            cx.close()
    except sqlite3.Error:
        return False


def ensure(cache_dir, url=DATA_URL, ttl=TTL, force=False):
    """Make sure cache_dir holds fresh copies; keep stale ones on failure."""
    os.makedirs(cache_dir, exist_ok=True)
    for name in FILES:
        dest = os.path.join(cache_dir, name)
        fresh = os.path.exists(dest) and time.time() - os.path.getmtime(dest) < ttl
        if fresh and not force:
            continue
        try:
            req = urllib.request.Request("%s/%s" % (url.rstrip("/"), name), headers={
                "User-Agent": "cavalera-forge-mcp/%s" % __version__})
            fd, tmp = tempfile.mkstemp(dir=cache_dir, suffix=".part")
            with os.fdopen(fd, "wb") as out, urllib.request.urlopen(req, timeout=60) as rep:
                while True:
                    chunk = rep.read(1 << 16)
                    if not chunk:
                        break
                    out.write(chunk)
            if not _valid(tmp):
                os.remove(tmp)
                raise RuntimeError("downloaded %s is not a valid database" % name)
            os.replace(tmp, dest)
            log.info("downloaded %s", name)
        except Exception as exc:  # noqa: BLE001  keep the stale copy
            if os.path.exists(dest):
                log.warning("refresh of %s failed, keeping the cached copy: %s", name, exc)
            else:
                raise
    return cache_dir
