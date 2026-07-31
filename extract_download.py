from __future__ import annotations

"""Téléchargement des archives ZIP et cache incrémental d'extraction."""

import io
import json
import threading
import zipfile
from pathlib import Path

import requests

from lib.logutil import log
from extract_parsing import process_pdf

TIMEOUT     = 30  # secondes par requête HTTP
MAX_WORKERS = 8   # téléchargements simultanés

CACHE_FILE = Path(__file__).parent / "zip_cache.json"

_log_lock = threading.Lock()


def _log(msg: str) -> None:
    with _log_lock:
        log(msg)


def download_zip(url: str) -> bytes | None:
    """Télécharge un ZIP en mémoire avec progression en temps réel."""
    try:
        r = requests.get(url, timeout=TIMEOUT, stream=True)
        r.raise_for_status()
        total_expected = int(r.headers.get("content-length", 0))
        chunks, total = [], 0
        last_pct = -1
        for chunk in r.iter_content(65536):
            chunks.append(chunk)
            total += len(chunk)
            if total_expected:
                pct = int(total / total_expected * 100)
                if pct >= last_pct + 10:
                    last_pct = pct
                    mb = total / 1024 / 1024
                    print(f"\r    ↓ {mb:.1f} Mo — {pct}%   ", end="", flush=True)
            else:
                mb = total / 1024 / 1024
                if int(mb) > int((total - len(chunk)) / 1024 / 1024):
                    print(f"\r    ↓ {mb:.0f} Mo…   ", end="", flush=True)
        print()  # saut de ligne après la progression
        log(f"    ✓ {total/1024/1024:.1f} Mo téléchargés")
        return b"".join(chunks)
    except Exception as e:
        print()
        log(f"    ✗ Erreur téléchargement : {e}")
        return None


def process_task(source: dict, year_int: int, zip_url: str, origin: str) -> tuple[list[dict], dict]:
    """Télécharge un ZIP et extrait ses décisions (exécuté dans un thread)."""
    label = f"{source['name']} [{year_int}]"
    _log(f"  ↓ [{origin}] {label}")
    local = {"zips": 1, "pdfs": 0, "decisions": 0, "errors": 0}
    results: list[dict] = []

    zip_bytes = download_zip(zip_url)
    if not zip_bytes:
        local["errors"] += 1
        return results, local

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
            _log(f"    → {label} : {len(pdf_names)} PDF")
            local["pdfs"] += len(pdf_names)
            for pdf_name in pdf_names:
                try:
                    decision = process_pdf(zf.read(pdf_name), pdf_name, source, year_int, zip_url)
                    if decision:
                        results.append(decision)
                        local["decisions"] += 1
                except Exception as e:
                    _log(f"    ✗ {pdf_name} : {e}")
                    local["errors"] += 1
    except zipfile.BadZipFile:
        _log(f"    ✗ {label} : archive ZIP corrompue")
        local["errors"] += 1

    return results, local


def load_zip_cache() -> dict:
    """Charge le cache des URLs déjà traitées : {cache_key → url}."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_zip_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
