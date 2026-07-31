from __future__ import annotations

"""Archivage des PDF de convocation et de l'historique des audiences passées."""

import io
import json
from datetime import date, datetime, timedelta
from pathlib import Path

import requests

from lib.logutil import log
from audiences_supabase import fetch_supabase_file, upload_pdf_to_supabase

ARCHIVE_WEEKS_KEPT = 12  # conserver les audiences passées 12 semaines dans l'archive

# ── PDF de convocation à archiver ─────────────────────────────────────────────
CONVOCATIONS_PDFS = [
    {"court": "Cour administrative",      "chambre": "",          "url": "https://justice.public.lu/downloads.jurad/Cour.pdf"},
    {"court": "Tribunal administratif",   "chambre": "1re ch.",   "url": "https://justice.public.lu/downloads.jurad/trib1.pdf"},
    {"court": "Tribunal administratif",   "chambre": "2e ch.",    "url": "https://justice.public.lu/downloads.jurad/trib2.pdf"},
    {"court": "Tribunal administratif",   "chambre": "3e ch.",    "url": "https://justice.public.lu/downloads.jurad/trib3.pdf"},
    {"court": "Tribunal administratif",   "chambre": "4e ch.",    "url": "https://justice.public.lu/downloads.jurad/trib4.pdf"},
    {"court": "Tribunal administratif",   "chambre": "5e ch.",    "url": "https://justice.public.lu/downloads.jurad/trib5.pdf"},
    {"court": "Tribunal administratif",   "chambre": "6e ch.",    "url": "https://justice.public.lu/downloads.jurad/trib6.pdf"},
]


def download_pdf_archive(out_dir: Path) -> list[dict]:
    """
    Télécharge les PDF de convocation et les archive dans archives/YYYY-WNN-{slug}.pdf.
    Retourne la liste des métadonnées pour archives/index.json.
    """
    archives_dir = out_dir / "archives"
    archives_dir.mkdir(exist_ok=True)

    today   = date.today()
    week_str = today.strftime("%Y-W%W")
    records  = []

    try:
        import pdfplumber  # noqa: F401 — vérifie la disponibilité
        has_pdfplumber = True
    except ImportError:
        has_pdfplumber = False
        log("  ⚠ pdfplumber non disponible — texte des PDF non extrait")

    for entry in CONVOCATIONS_PDFS:
        slug = (entry["court"] + "-" + entry["chambre"]).replace(" ", "-").replace(".", "").lower()
        filename = f"{week_str}-{slug}.pdf"
        dest = archives_dir / filename

        log(f"  ↓ {entry['court']} {entry['chambre']} → {filename}")
        try:
            r = requests.get(entry["url"], timeout=20, headers={"User-Agent": "Mozilla/5.0"})
            r.raise_for_status()
            dest.write_bytes(r.content)
        except Exception as e:
            log(f"    ✗ Erreur téléchargement : {e}")
            continue

        # Copie en ligne (bucket privé) pour que la rédaction y accède
        # même quand la machine qui a lancé le scraping est éteinte
        if upload_pdf_to_supabase(filename, r.content):
            log(f"    ✓ PDF poussé vers Supabase Storage")

        # Extraction texte pour recherche
        text = ""
        if has_pdfplumber:
            try:
                with pdfplumber.open(io.BytesIO(r.content)) as pdf:
                    pages = pdf.pages[:6]
                    text = "\n".join(p.extract_text() or "" for p in pages)
            except Exception as e:
                log(f"    ⚠ Extraction texte : {e}")

        # Snippet (premières 300 chars)
        snippet = " ".join(text.split())[:300] if text else ""

        records.append({
            "court":      entry["court"],
            "chambre":    entry["chambre"],
            "week":       week_str,
            "downloaded": today.isoformat(),
            "path":       f"archives/{filename}",
            "text":       text,
            "snippet":    snippet,
        })

    # Lire l'index existant : fichier local + blob Supabase (le CI repart
    # d'un workspace vide — l'historique en ligne fait foi) et fusionner
    index_path = archives_dir / "index.json"
    existing: list[dict] = []
    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    remote = fetch_supabase_file("archives_index")
    if isinstance(remote, list):
        local_keys = {(r["court"], r["chambre"], r["week"]) for r in existing}
        existing += [r for r in remote if (r.get("court"), r.get("chambre"), r.get("week")) not in local_keys]

    # Clé d'unicité : court + chambre + week
    existing_keys = {(r["court"], r["chambre"], r["week"]) for r in existing}
    new_records = [r for r in records if (r["court"], r["chambre"], r["week"]) not in existing_keys]
    all_records = existing + new_records
    # Tri : semaines décroissantes
    all_records.sort(key=lambda x: (x["week"], x["court"], x["chambre"]), reverse=True)

    index_path.write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n✓ archives/index.json → {len(all_records)} entrées ({len(new_records)} nouvelles)")
    return all_records


def update_audiences_archive(out_dir: Path, old_events: list[dict], today: date) -> int:
    """
    Déplace vers audiences_archive.json les audiences de l'ancien audiences.json
    dont la date est désormais passée (elles sortiraient sinon silencieusement
    de la fenêtre glissante de WEEKS_AHEAD semaines générée à chaque exécution).
    Conserve un historique glissant de ARCHIVE_WEEKS_KEPT semaines.
    """
    archive_path = out_dir / "audiences_archive.json"
    existing: list[dict] = []
    if archive_path.exists():
        try:
            existing = json.loads(archive_path.read_text(encoding="utf-8")).get("events", [])
        except Exception:
            existing = []
    if not existing:
        # CI : workspace vide → repartir de l'historique en ligne
        remote = fetch_supabase_file("audiences_archive")
        if isinstance(remote, dict) and isinstance(remote.get("events"), list):
            existing = remote["events"]

    existing_uids = {e["uid"] for e in existing}
    today_str = today.isoformat()
    newly_past = [e for e in old_events if e["date"] < today_str and e["uid"] not in existing_uids]

    merged = existing + newly_past
    cutoff = (today - timedelta(weeks=ARCHIVE_WEEKS_KEPT)).isoformat()
    merged = [e for e in merged if e["date"] >= cutoff]
    merged.sort(key=lambda e: (e["date"], e["horaire"]), reverse=True)

    archive_path.write_text(json.dumps({
        "updated_at":   datetime.now().isoformat(),
        "total_events": len(merged),
        "events":       merged,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"✓ audiences_archive.json → {len(merged)} audiences passées ({len(newly_past)} nouvellement archivées)")
    return len(newly_past)
