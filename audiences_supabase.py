from __future__ import annotations

"""Lecture/écriture des blobs d'audiences dans Supabase (table `files`, bucket `archives`)."""

from datetime import datetime

import requests

from lib.logutil import log
from lib.supabase_client import get_supabase_credentials


def upload_pdf_to_supabase(filename: str, content: bytes) -> bool:
    """Upload (upsert) un PDF de convocation dans le bucket privé `archives`."""
    env = get_supabase_credentials()
    if not env:
        return False
    url, key = env
    try:
        r = requests.post(
            f"{url}/storage/v1/object/archives/{filename}",
            headers={
                "apikey":        key,
                "Authorization": f"Bearer {key}",
                "Content-Type":  "application/pdf",
                "x-upsert":      "true",
            },
            data=content,
            timeout=60,
        )
        if r.status_code in (200, 201):
            return True
        log(f"    ✗ Storage {filename} : {r.status_code} — {r.text[:150]}")
    except Exception as e:
        log(f"    ✗ Storage {filename} : {e}")
    return False


def fetch_supabase_file(file_key: str):
    """Lit un blob de la table files (service_role, contourne RLS)."""
    env = get_supabase_credentials()
    if not env:
        return None
    url, key = env
    try:
        r = requests.get(
            f"{url}/rest/v1/files?key=eq.{file_key}&select=content",
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=30,
        )
        if r.status_code == 200:
            rows = r.json()
            if rows:
                return rows[0].get("content")
    except Exception as e:
        log(f"  ⚠ Lecture files/{file_key} : {e}")
    return None


def push_files_to_supabase(payloads: dict) -> None:
    """
    Pousse les blobs de données (audiences, archives, ics) vers la table
    `files` de Supabase. Les fichiers JSON ne sont plus publiés sur GitHub
    Pages : Supabase (lecture réservée @reporter.lu) est la seule source
    de données en ligne.
    """
    env = get_supabase_credentials()
    if not env:
        log("  ⚠ Supabase non configuré (SUPABASE_URL / SUPABASE_KEY) — blobs non poussés")
        return
    url, key = env

    headers = {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates",
    }
    now = datetime.now().isoformat()
    rows = [{"key": k, "content": v, "updated_at": now} for k, v in payloads.items()]
    try:
        r = requests.post(f"{url}/rest/v1/files", headers=headers, json=rows, timeout=60)
        if r.status_code in (200, 201):
            log(f"  ✓ Supabase files : {', '.join(payloads.keys())}")
        else:
            log(f"  ✗ Supabase files : {r.status_code} — {r.text[:200]}")
    except Exception as e:
        log(f"  ✗ Supabase files : {e}")
