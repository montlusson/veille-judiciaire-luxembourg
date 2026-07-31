#!/usr/bin/env python3
from __future__ import annotations
"""
extract_decisions.py
Pipeline d'extraction des décisions judiciaires luxembourgeoises
Sources : data.public.lu / Administration judiciaire
Sortie   : decisions.json (chargé par veille-judiciaire-luxembourg.html)

Usage :
  pip install pdfplumber requests
  python3 extract_decisions.py

Options d'environnement (optionnelles, pour Phase 2 — Supabase) :
  SUPABASE_URL=https://xxxx.supabase.co
  SUPABASE_KEY=votre-anon-key
"""

import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from lib.logutil import log
from extract_sources import SOURCES, YEARS, get_slug, resolve_zip_urls
from extract_parsing import _make_id
from extract_download import MAX_WORKERS, load_zip_cache, save_zip_cache, process_task
from extract_supabase import push_to_supabase

OUTPUT_FILE = Path(__file__).parent / "decisions.json"


def load_existing_decisions() -> list[dict]:
    """Charge les décisions existantes depuis decisions.json, ou decisions_index.json en fallback."""
    if OUTPUT_FILE.exists():
        try:
            data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
            return data.get("decisions", [])
        except Exception:
            pass
    # Fallback : decisions_index.json (sans fulltext) — utilisé en CI/CD
    index_file = OUTPUT_FILE.parent / "decisions_index.json"
    if index_file.exists():
        try:
            data = json.loads(index_file.read_text(encoding="utf-8"))
            log("  ℹ decisions.json absent — chargement depuis decisions_index.json (sans fulltext)")
            return data.get("decisions", [])
        except Exception:
            pass
    return []


def main() -> None:
    log("═══════════════════════════════════════════════════════")
    log("  Pipeline d'extraction — Juridictions luxembourgeoises")
    log(f"  Démarrage : {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    log("═══════════════════════════════════════════════════════\n")

    # ── Chargement de l'état existant ──────────────────────────────────────────
    zip_cache = load_zip_cache()          # {cache_key → url déjà traitée}
    existing  = load_existing_decisions() # décisions déjà indexées

    stats = {"sources": len(SOURCES), "zips": 0, "pdfs": 0, "decisions": 0,
             "errors": 0, "skipped": 0}

    # ── Phase 1 : résolution des URLs (séquentielle, ~30 appels API légers) ──
    log("── Phase 1 : résolution des URLs via API data.public.lu ──")
    tasks: list[tuple[dict, int, str, str]] = []  # (source, year_int, url, origin)
    for source in SOURCES:
        slug = get_slug(source)
        dynamic_urls = resolve_zip_urls(slug) if slug else {}
        for year_key in YEARS:
            year_int = int(year_key.replace("zip", ""))
            if year_int in dynamic_urls:
                tasks.append((source, year_int, dynamic_urls[year_int], "API"))
            elif source.get(year_key):
                tasks.append((source, year_int, source[year_key], "fallback"))

    # ── Filtre incrémental : on saute les ZIPs dont l'URL n'a pas changé ──────
    # Clé de cache = "nom_source::année" → URL traitée lors du dernier run
    todo   = []   # tâches à exécuter
    skip   = set()# (source_name, year_int) → réutiliser depuis existing
    for s, yi, url, orig in tasks:
        key = f"{s['name']}::{yi}"
        if zip_cache.get(key) == url:
            skip.add((s["name"], yi))
            stats["skipped"] += 1
        else:
            todo.append((s, yi, url, orig))

    n_skip = len(skip)
    n_todo = len(todo)
    log(f"  → {n_skip} archives inchangées (sautées) | {n_todo} à télécharger\n")

    # ── Phase 2 : téléchargement + extraction (uniquement les ZIPs nouveaux) ──
    new_decisions: list[dict] = []
    reprocessed: set[tuple[str, int]] = set()  # paires (jur, year) re-extraites

    if todo:
        log(f"── Phase 2 : téléchargement parallèle ({MAX_WORKERS} workers) ──")
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
            futures = {pool.submit(process_task, s, yi, url, orig): (s, yi, url)
                       for s, yi, url, orig in todo}
            for future in as_completed(futures):
                s, yi, url = futures[future]
                decisions, local = future.result()
                new_decisions.extend(decisions)
                reprocessed.add((s["name"], yi))
                # Mettre à jour le cache seulement si pas d'erreur
                if local["errors"] == 0 or decisions:
                    zip_cache[f"{s['name']}::{yi}"] = url
                stats["zips"]      += local["zips"]
                stats["pdfs"]      += local["pdfs"]
                stats["decisions"] += local["decisions"]
                stats["errors"]    += local["errors"]
    else:
        log("── Phase 2 : aucun téléchargement nécessaire (cache à jour) ──")

    # ── Fusion : conserver les existantes non-retraitées + ajouter les nouvelles
    kept = [d for d in existing
            if (d.get("jur"), d.get("source_year")) not in reprocessed]
    all_decisions = kept + new_decisions

    # Migration des anciens IDs (format "nom-année-fichier") vers le hash stable.
    # Ne PAS recalculer un hash déjà au bon format : les décisions rechargées depuis
    # decisions_index.json (excerpt tronqué, sans fulltext) produiraient un hash
    # différent → doublons dans Supabase au prochain push.
    _HASH_ID = re.compile(r"^[0-9a-f]{16}$")
    for d in all_decisions:
        if not _HASH_ID.match(str(d.get("id", ""))):
            d["id"] = _make_id(d.get("jur", ""), d.get("source_year", 0),
                               d.get("ref", ""), d.get("excerpt", ""), d.get("fulltext", ""))

    all_decisions.sort(key=lambda d: d.get("date") or "", reverse=True)

    # ── Sauvegarde ─────────────────────────────────────────────────────────────
    output = {
        "generated_at": datetime.now().isoformat(),
        "total":        len(all_decisions),
        "stats":        stats,
        "decisions":    all_decisions,
    }
    OUTPUT_FILE.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    # Manifeste léger pour le cache IndexedDB du module HTML
    meta_file = OUTPUT_FILE.parent / "decisions_meta.json"
    meta_file.write_text(
        json.dumps({"generated_at": output["generated_at"], "total": output["total"]}, ensure_ascii=False),
        encoding="utf-8"
    )

    # Index statique pour GitHub Pages (sans fulltext, excerpt tronqué à 200 chars)
    _keep = {'id','ref','date','jur','group','type','source_year'}
    index_decisions = []
    for d in all_decisions:
        row = {k: d.get(k) for k in _keep}
        row['excerpt'] = (d.get('excerpt') or '')[:200]
        ent = d.get('entities') or {}
        row['entities'] = {'societes': ent.get('societes', []), 'montants': ent.get('montants', [])}
        index_decisions.append(row)
    index_file = OUTPUT_FILE.parent / "decisions_index.json"
    index_file.write_text(
        json.dumps({"generated_at": output["generated_at"], "total": len(index_decisions), "decisions": index_decisions}, ensure_ascii=False),
        encoding="utf-8"
    )
    log(f"  Index   : {index_file} ({index_file.stat().st_size / 1024 / 1024:.1f} MB)")

    log(f"\n═══════════════════════════════════════════════════════")
    log(f"  Terminé : {len(all_decisions)} décisions ({stats['decisions']} nouvelles, "
        f"{stats['skipped']} archives sautées)")
    log(f"  Sources : {stats['sources']} | ZIPs traités : {stats['zips']} | PDF : {stats['pdfs']}")
    if stats['errors']:
        log(f"  Erreurs : {stats['errors']}")
    log(f"  Fichier : {OUTPUT_FILE}")
    log(f"═══════════════════════════════════════════════════════")

    # ── Poussée Supabase ────────────────────────────────────────────────────
    # --push-new     (CI hebdo) : pousse UNIQUEMENT les décisions fraîchement
    #                extraites (fulltext complet). Les lignes Supabase des
    #                archives inchangées ne sont pas touchées → fulltext intact.
    # --push-supabase (local)   : pousse tout all_decisions. Requiert
    #                decisions.json (fulltext) — jamais en CI, où
    #                load_existing_decisions() lirait decisions_index.json
    #                (sans fulltext) et écraserait le fulltext Supabase.
    #
    # Le cache n'est enregistré qu'APRÈS un push réussi : si Supabase est
    # injoignable (projet gratuit en pause), les archives ne sont pas marquées
    # « traitées » et seront ré-extraites + repoussées au prochain run.
    push_requested = "--push-new" in sys.argv or "--push-supabase" in sys.argv
    push_ok = True
    if "--push-new" in sys.argv:
        if new_decisions:
            push_ok = push_to_supabase(new_decisions, output["generated_at"])
        else:
            log("  Supabase : aucune nouvelle décision — push ignoré")
    elif "--push-supabase" in sys.argv:
        if not OUTPUT_FILE.exists():
            log("  ✗ --push-supabase requiert decisions.json (fulltext). Lancez d'abord le script sans ce flag.")
            sys.exit(1)
        push_ok = push_to_supabase(all_decisions, output["generated_at"])
    else:
        log("  Supabase push ignoré (--push-new en CI, --push-supabase en local)")

    if push_requested and not push_ok:
        log("  ⚠ Cache NON enregistré (push échoué) — ré-extraction au prochain run")
        sys.exit(1)
    save_zip_cache(zip_cache)


if __name__ == "__main__":
    main()
