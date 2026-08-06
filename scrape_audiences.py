#!/usr/bin/env python3
"""
scrape_audiences.py
Récupère les calendriers d'audiences des tribunaux luxembourgeois
Source : https://justice.public.lu/fr/audiences.html
Sortie : audiences.json + audiences.ics (importable dans tout agenda)

Usage :
  python3 scrape_audiences.py
"""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from lib.logutil import log
from audiences_schedule import (
    JURIDICTIONS, WEEKS_AHEAD,
    fetch_page, parse_table_rows, parse_text_content, parse_ul_schedules,
    generate_occurrences,
)
from audiences_ical import build_ical
from audiences_pdf import update_audiences_archive
from audiences_supabase import fetch_supabase_file, push_files_to_supabase


def main() -> None:
    log("═══════════════════════════════════════════════════════")
    log("  Scraper audiences judiciaires — justice.public.lu")
    log("═══════════════════════════════════════════════════════\n")

    today   = date.today()
    raw     = []   # séances récurrentes brutes
    events  = []   # occurrences calculées avec dates réelles

    out_dir = Path(__file__).parent

    # Charge l'ancien audiences.json AVANT de l'écraser : sert à détecter les
    # nouvelles entrées et à archiver celles devenues passées.
    old_audiences_path = out_dir / "audiences.json"
    old_events: list[dict] = []
    if old_audiences_path.exists():
        try:
            old_events = json.loads(old_audiences_path.read_text(encoding="utf-8")).get("events", [])
        except Exception:
            old_events = []
    if not old_events:
        # CI : workspace vide → comparer avec la dernière extraction en ligne
        remote = fetch_supabase_file("audiences")
        if isinstance(remote, dict) and isinstance(remote.get("events"), list):
            old_events = remote["events"]

    for jur in JURIDICTIONS:
        log(f"── {jur['nom']} ──")
        soup = fetch_page(jur["slug"])
        if not soup:
            continue

        entries = parse_table_rows(soup, jur["nom"])
        if not entries:
            entries = parse_text_content(soup, jur["nom"])
        if not entries:
            entries = parse_ul_schedules(soup, jur["nom"])

        log(f"  → {len(entries)} séance(s) récurrente(s) trouvée(s)")
        raw.extend(entries)

        for entry in entries:
            occurrences = generate_occurrences(entry["jours"], entry["horaire"], today)
            for occ in occurrences:
                events.append({
                    "uid":         hashlib.sha1(f"{entry['juridiction']}::{occ.isoformat()}::{entry['chambre']}::{entry['horaire']}".encode()).hexdigest()[:32] + "@vj-lux",
                    "date":        occ.isoformat(),
                    "juridiction": entry["juridiction"],
                    "chambre":     entry["chambre"],
                    "horaire":     entry["horaire"],
                    "salle":       entry["salle"],
                    "jours_txt":   entry["jours_txt"],
                })

    events.sort(key=lambda e: (e["date"], e["horaire"]))

    # ── Détection de nouvelles entrées ──────────────────────
    old_uids = {e["uid"] for e in old_events}
    new_uids = {e["uid"] for e in events}
    brand_new = new_uids - old_uids
    if old_events:
        log(f"\n→ {len(brand_new)} nouvelle(s) audience(s) détectée(s) depuis la dernière extraction")
    else:
        log("\n→ première extraction, pas de comparaison possible")

    # ── audiences.json ─────────────────────────────────────
    output = {
        "generated_at": datetime.now().isoformat(),
        "total_events":  len(events),
        "total_seances": len(raw),
        "events":        events,
        "seances":       raw,
    }
    json_path = out_dir / "audiences.json"
    json_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n✓ audiences.json → {len(events)} occurrences sur {WEEKS_AHEAD} semaines")

    # ── audiences.ics ──────────────────────────────────────
    ical = build_ical(events)
    ics_path = out_dir / "audiences.ics"
    ics_path.write_text(ical, encoding="utf-8")
    log(f"✓ audiences.ics  → importable dans Apple Agenda, Google Calendar, Outlook")

    # ── Archives des audiences passées ──────────────────────
    log("\n── Archivage des audiences passées ──")
    update_audiences_archive(out_dir, old_events, today)

    # NOTE : le téléchargement automatisé des PDF de convocation nominatifs
    # a été retiré (risque juridique — disclaimer restreignant l'usage aux
    # avocats des parties). Les convocations sont désormais déposées
    # volontairement par les journalistes depuis l'app (onglet Audiences →
    # "Convocations déposées"), qui alimente directement la table Supabase
    # `affaires` — voir affaires-schema.sql.

    # ── Push Supabase (table files) — seule source de données en ligne ──
    log("\n── Push Supabase (table files) ──")
    try:
        archive_events = json.loads((out_dir / "audiences_archive.json").read_text(encoding="utf-8"))
    except Exception:
        archive_events = {"events": []}
    push_files_to_supabase({
        "audiences":         output,
        "audiences_archive": archive_events,
        "audiences_ics":     {"ics": ical},
    })

    log(f"\n═══════════════════════════════════════════════════════")
    log(f"  Terminé : {len(events)} audiences générées ({len(JURIDICTIONS)} juridictions)")
    log(f"═══════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
