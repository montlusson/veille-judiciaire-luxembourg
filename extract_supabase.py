from __future__ import annotations

"""Envoi des décisions extraites vers Supabase (table `decisions`)."""

import time

import requests

from lib.logutil import log
from lib.supabase_client import get_supabase_credentials


def push_to_supabase(decisions: list[dict], generated_at: str) -> bool:
    """Envoie les décisions vers Supabase via service_role key.
    Renvoie True si l'envoi a réussi (aucun lot en erreur), False sinon —
    le cache n'est enregistré qu'en cas de succès pour ne pas perdre des
    décisions si le projet est injoignable (ex. projet gratuit en pause)."""
    env = get_supabase_credentials()
    if not env:
        log("  ⚠ Supabase non configuré (SUPABASE_URL / SUPABASE_KEY manquants) — ignoré")
        return False
    url, key = env

    log(f"\n── Envoi vers Supabase ({len(decisions)} décisions) ──")

    # Colonnes envoyées — on exclut les clés internes (_demo, archived)
    COLS = {"id", "ref", "date", "jur", "group", "type", "excerpt", "fulltext", "entities", "source_year"}

    def clean(d: dict) -> dict:
        row = {k: v for k, v in d.items() if k in COLS}
        # S'assurer que entities est un dict (JSONB)
        if not isinstance(row.get("entities"), dict):
            row["entities"] = {}
        return row

    headers = {
        "apikey":        key,
        "Authorization": f"Bearer {key}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates",
    }

    # Dédupliquer par id (évite l'erreur ON CONFLICT avec doublons intra-lot)
    seen = {}
    for d in decisions:
        seen[d["id"]] = d
    decisions = list(seen.values())

    # Upsert par lots de 100 (payloads fulltext volumineux → timeout à 200)
    batch_size = 100
    errors = 0
    total_batches = (len(decisions) - 1) // batch_size + 1
    for i in range(0, len(decisions), batch_size):
        batch = [clean(d) for d in decisions[i:i + batch_size]]
        batch_num = i // batch_size + 1
        for attempt in range(3):
            try:
                r = requests.post(f"{url}/rest/v1/decisions", headers=headers, json=batch, timeout=120)
                if r.status_code in (200, 201):
                    log(f"  ✓ Lot {batch_num}/{total_batches} ({len(batch)} entrées)")
                    break
                else:
                    errors += 1
                    log(f"  ✗ Lot {batch_num} : {r.status_code} — {r.text[:200]}")
                    break
            except requests.exceptions.RequestException as e:
                # Couvre timeout ET erreurs réseau/DNS (projet en pause → injoignable)
                if attempt < 2:
                    log(f"  ↻ Lot {batch_num} réseau — retry {attempt+2}/3…")
                    time.sleep(5 * (attempt + 1))
                else:
                    errors += 1
                    log(f"  ✗ Lot {batch_num} : échec réseau après 3 tentatives — {str(e)[:120]}")

    # Mettre à jour la table meta (timestamp)
    try:
        meta_payload = [{"key": "last_generated", "value": generated_at, "updated_at": generated_at}]
        r = requests.post(f"{url}/rest/v1/meta", headers={**headers, "Prefer": "resolution=merge-duplicates"}, json=meta_payload, timeout=10)
        if r.status_code in (200, 201):
            log(f"  ✓ Table meta mise à jour ({generated_at})")
        else:
            log(f"  ✗ Meta : {r.status_code} — {r.text[:100]}")
    except requests.exceptions.RequestException as e:
        errors += 1
        log(f"  ✗ Meta : échec réseau — {str(e)[:120]}")

    if errors == 0:
        log(f"  ✓ Supabase synchronisé — {len(decisions)} décisions")
        return True
    log(f"  ⚠ {errors} lot(s) en erreur — projet injoignable (pause ?) ou droits service_role")
    return False
