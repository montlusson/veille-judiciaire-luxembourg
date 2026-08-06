from __future__ import annotations

"""Archivage de l'historique des audiences passées (horaires récurrents, non nominatif).

Le téléchargement automatisé des PDF de convocation nominatifs a été retiré
(risque juridique — disclaimer restreignant l'usage aux avocats des parties).
Les convocations sont désormais déposées volontairement par les journalistes
depuis l'app (onglet Audiences → "Convocations déposées")."""

import json
from datetime import date, datetime, timedelta
from pathlib import Path

from lib.logutil import log
from audiences_supabase import fetch_supabase_file

ARCHIVE_WEEKS_KEPT = 12  # conserver les audiences passées 12 semaines dans l'archive


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
