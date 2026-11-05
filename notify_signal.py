#!/usr/bin/env python3
from __future__ import annotations
"""
notify_signal.py
Résumé des nouvelles décisions envoyé dans un groupe Signal de la rédaction.

À lancer APRÈS l'extraction (extract_decisions.py --push-new). Rien n'est envoyé s'il n'y a
aucune nouveauté : un message par run qui en trouve, aucun sinon.

Principe : une « nouveauté » est une ligne de la table `decisions` dont `created_at` est
postérieur au dernier envoi (mémorisé dans la table `meta`, clé `signal_last_notified`). Un
envoi raté ne perd rien : la date n'avance qu'après un envoi réussi, le message suivant
regroupe alors tout ce qui s'est accumulé. Les décisions simplement renvoyées par une archive
régénérée gardent leur ancienne `created_at` et ne comptent pas.

Le message ne contient que des chiffres par juridiction et un lien vers le module : aucun
nom, aucun extrait. Il vaut aussi pour un dépôt public (les journaux GitHub Actions le sont).

Premier lancement : la date de référence est posée sans rien envoyer (sinon tout le stock
existant partirait d'un coup).

Variables d'environnement
  SUPABASE_URL, SUPABASE_KEY   les mêmes que l'extraction (clé service_role)
  SIGNAL_API_URL               adresse de signal-cli-rest-api, ex. http://localhost:8080
  SIGNAL_SENDER                numéro Signal émetteur, ex. +352621000000
  SIGNAL_GROUP_ID              identifiant du groupe, de la forme group.XXXX…
  MODULE_URL                   (facultatif) lien ajouté en fin de message
  SIGNAL_API_TOKEN             (facultatif) jeton « Bearer » si l'API est derrière un proxy
  SIGNAL_QUIET_MINUTES         (facultatif, 10) délai sans nouvelle arrivée avant d'envoyer
Si SIGNAL_API_URL, SIGNAL_SENDER ou SIGNAL_GROUP_ID manque, le script ne fait rien (sortie 0).

Option
  --dry-run   compte et affiche le message sans l'envoyer ni avancer la date de référence

Où le faire tourner
  Sur le NAS de la rédaction, PAS dans GitHub Actions : l'extraction et l'envoi sont deux étapes
  indépendantes, reliées seulement par la base. L'extraction (GitHub Actions) écrit dans le
  Supabase du NAS ; ce script, lancé régulièrement sur le NAS, lit cette même base et parle à un
  serveur Signal du réseau interne. Rien n'est exposé sur Internet pour cela.
  Planifier par exemple toutes les 15 minutes (tâche planifiée du NAS ou petit conteneur).
  Comme l'état est dans la base (« depuis le dernier envoi »), un NAS redémarré ou une fenêtre
  manquée ne perd rien : le passage suivant envoie tout ce qui s'est accumulé.

Un message par run, pas un par lot
  Un run écrit ses décisions par petits lots en quelques minutes. Pour ne pas envoyer un message
  par lot, le script attend que plus rien ne soit arrivé depuis SIGNAL_QUIET_MINUTES (10 par
  défaut) : tant que des décisions arrivent encore, il ne fait rien et reprendra au passage suivant.

Réglages côté NAS
  1. SUPABASE_URL / SUPABASE_KEY : adresse INTERNE de l'API de l'instance auto-hébergée et sa
     clé service_role (pas celles du projet managé actuel). Garder la clé hors du dépôt, dans un
     fichier d'environnement lisible par le seul compte qui lance le script.
  2. Le schéma doit être installé sur cette instance : le script lit decisions.created_at et
     lit/écrit la table meta (supabase-schema.sql).
  3. Signal : serveur signal-cli-rest-api (mode json-rpc, données sur un volume persistant et
     SAUVEGARDÉ de façon chiffrée : il contient les clés du compte). Lier un compte Signal DÉDIÉ
     à la rédaction (numéro à part, pas un compte personnel) en ouvrant
     <serveur>/v1/qrcodelink?device_name=veille et en scannant le code depuis Signal > Appareils
     liés ; ajouter ce compte au groupe ; lire l'identifiant du groupe :
       curl <serveur>/v1/groups/<numéro>      (champ « id », de la forme group.…)
     Ne jamais publier ce serveur hors du réseau interne.
  4. MODULE_URL : l'adresse du module telle que les journalistes y accèdent.
  5. Si l'API Supabase est servie en HTTPS avec un certificat interne, le module `requests` devra
     connaître l'autorité de certification.

Ce qui reste sur GitHub Actions : l'extraction, le scraping des audiences, le cache d'URLs et
l'alerte « aucune nouveauté depuis 14 jours » (job `fraicheur`) ; ce script ne les remplace pas.

Le format exact de l'API et l'envoi vers un groupe sont à vérifier lors du premier essai
(--dry-run d'abord, puis un envoi réel dans un groupe de test) : ce script n'a pas pu être testé
contre un vrai serveur Signal.
"""

import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone

import requests

from lib.logutil import log
from lib.supabase_client import get_supabase_credentials

META_KEY = "signal_last_notified"
MAX_LINES = 8          # juridictions listées ; les suivantes sont regroupées
PAGE = 1000            # plafond PostgREST par requête
TIMEOUT = 30


def _headers(key: str) -> dict:
    return {"apikey": key, "Authorization": f"Bearer {key}"}


def read_last(url: str, key: str) -> str | None:
    """Date du dernier envoi (ISO 8601), ou None si jamais envoyé."""
    r = requests.get(f"{url}/rest/v1/meta", headers=_headers(key),
                     params={"select": "value", "key": f"eq.{META_KEY}"}, timeout=TIMEOUT)
    r.raise_for_status()
    rows = r.json()
    return rows[0]["value"] if rows else None


def write_last(url: str, key: str, value: str) -> None:
    r = requests.post(f"{url}/rest/v1/meta", params={"on_conflict": "key"},
                      headers={**_headers(key), "Content-Type": "application/json",
                               "Prefer": "resolution=merge-duplicates"},
                      json=[{"key": META_KEY, "value": value}], timeout=TIMEOUT)
    r.raise_for_status()


def fetch_new(url: str, key: str, since: str) -> list[dict]:
    """Décisions arrivées après `since` : [{created_at, jur}], par ordre d'arrivée."""
    out: list[dict] = []
    start = 0
    while True:
        r = requests.get(
            f"{url}/rest/v1/decisions",
            headers={**_headers(key), "Range-Unit": "items", "Range": f"{start}-{start + PAGE - 1}"},
            params={"select": "created_at,jur", "created_at": f"gt.{since}", "order": "created_at.asc,id.asc"},
            timeout=TIMEOUT)
        r.raise_for_status()
        rows = r.json()
        out.extend(rows)
        if len(rows) < PAGE:
            return out
        start += PAGE


def parse_ts(value: str) -> datetime:
    """Date ISO 8601 de PostgREST → datetime UTC. Tolère « Z » et un nombre quelconque de
    décimales (datetime.fromisoformat de Python < 3.11 n'accepte que 3 ou 6)."""
    v = str(value).strip().replace("Z", "+00:00")
    v = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], v, count=1)
    dt = datetime.fromisoformat(v)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _clean(text: str) -> str:
    """Une seule ligne, sans caractères de contrôle, longueur bornée."""
    return re.sub(r"[\x00-\x1f\x7f]+", " ", str(text or "")).strip()[:80] or "Juridiction inconnue"


def build_message(rows: list[dict], module_url: str = "") -> str:
    """Texte du message : total, détail par juridiction (les plus fournies d'abord), lien."""
    total = len(rows)
    counts = Counter(_clean(r.get("jur")) for r in rows)
    ranked = counts.most_common()
    head = f"Veille judiciaire — {total} nouvelle{'s' if total > 1 else ''} décision{'s' if total > 1 else ''}"
    lines = [head]
    for jur, n in ranked[:MAX_LINES]:
        lines.append(f"• {jur} : {n}")
    rest = ranked[MAX_LINES:]
    if rest:
        n_rest = sum(n for _, n in rest)
        lines.append(f"• {len(rest)} autre{'s' if len(rest) > 1 else ''} juridiction{'s' if len(rest) > 1 else ''} : {n_rest}")
    if module_url:
        lines.append("")
        lines.append(module_url)
    return "\n".join(lines)


def send_signal(api_url: str, sender: str, recipient: str, message: str, token: str = "") -> None:
    """Envoie `message` au groupe via signal-cli-rest-api (POST /v2/send)."""
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(f"{api_url.rstrip('/')}/v2/send", headers=headers, timeout=TIMEOUT,
                      json={"message": message, "number": sender, "recipients": [recipient]})
    if r.status_code not in (200, 201):
        raise RuntimeError(f"HTTP {r.status_code} — {r.text[:160]}")


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv
    api_url = (os.environ.get("SIGNAL_API_URL") or "").strip()
    sender = (os.environ.get("SIGNAL_SENDER") or "").strip()
    group = (os.environ.get("SIGNAL_GROUP_ID") or "").strip()
    module_url = (os.environ.get("MODULE_URL") or "").strip()
    token = (os.environ.get("SIGNAL_API_TOKEN") or "").strip()
    try:
        quiet = timedelta(minutes=float(os.environ.get("SIGNAL_QUIET_MINUTES", "10")))
    except ValueError:
        quiet = timedelta(minutes=10)

    if not dry and not (api_url and sender and group):
        log("Signal non configuré (SIGNAL_API_URL / SIGNAL_SENDER / SIGNAL_GROUP_ID) — ignoré")
        return 0
    creds = get_supabase_credentials()
    if not creds:
        log("Supabase non configuré (SUPABASE_URL / SUPABASE_KEY) — ignoré")
        return 0
    url, key = creds

    try:
        last = read_last(url, key)
        if last is None:
            if dry:
                log("Première exécution : la date de référence serait posée à l'instant, sans envoi.")
                return 0
            write_last(url, key, datetime.now(timezone.utc).isoformat())
            log("Première exécution : date de référence posée, rien envoyé")
            return 0
        rows = fetch_new(url, key, last)
    except requests.RequestException as e:
        log(f"Supabase injoignable : {e.__class__.__name__} — rien envoyé, nouvel essai au prochain run")
        return 1

    if not rows:
        log("Aucune nouvelle décision depuis le dernier envoi — pas de message")
        return 0

    newest = max(r["created_at"] for r in rows)
    idle = datetime.now(timezone.utc) - parse_ts(newest)
    waiting = quiet > timedelta(0) and idle < quiet     # délai à 0 = jamais d'attente

    if waiting and not dry:
        log(f"{len(rows)} décision(s) arrivée(s), la dernière il y a {max(0, int(idle.total_seconds() // 60))} min : "
            "on attend la fin du run avant d'envoyer")
        return 0

    message = build_message(rows, module_url)
    log(f"{len(rows)} nouvelle(s) décision(s) à signaler")
    if dry:
        print("--- message (dry-run) ---\n" + message + "\n--- fin ---")
        if waiting:
            print("(un envoi réel attendrait encore la fin du run : des décisions arrivent toujours)")
        return 0

    try:
        send_signal(api_url, sender, group, message, token)
    except (requests.RequestException, RuntimeError) as e:
        log(f"Envoi Signal échoué : {e.__class__.__name__} {str(e)[:160]} — la date n'avance pas, nouvel essai au prochain run")
        return 1

    try:
        write_last(url, key, newest)
    except requests.RequestException as e:
        log(f"Message envoyé, mais date de référence non enregistrée ({e.__class__.__name__}) : "
            "le prochain run pourrait renvoyer les mêmes nouveautés")
        return 1
    log("Message Signal envoyé")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
