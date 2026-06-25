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

import json
import re
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://justice.public.lu"

JURIDICTIONS = [
    {"slug": "cour-constitutionnelle",          "nom": "Cour constitutionnelle"},
    {"slug": "cour-cassation",                   "nom": "Cour de Cassation"},
    {"slug": "cour-appel",                       "nom": "Cour d'appel"},
    {"slug": "tribunal-arrondissement-luxembourg","nom": "Tribunal d'arrondissement de Luxembourg"},
    {"slug": "tribunal-arrondissement-diekirch", "nom": "Tribunal d'arrondissement de Diekirch"},
    {"slug": "justice-paix-luxembourg",          "nom": "Justice de Paix de Luxembourg"},
    {"slug": "justice-paix-esch-sur-alzette",    "nom": "Justice de Paix d'Esch-sur-Alzette"},
    {"slug": "justice-paix-diekirch",            "nom": "Justice de Paix de Diekirch"},
    {"slug": "cour-administrative",              "nom": "Cour administrative"},
    {"slug": "tribunal-administratif",           "nom": "Tribunal administratif"},
    {"slug": "conseil-superieur-securite-sociale","nom": "Conseil supérieur de la sécurité sociale"},
    {"slug": "conseil-arbitral-securite-sociale", "nom": "Conseil arbitral de la sécurité sociale"},
]

# Mapping français → numéro de jour (0=lundi, 6=dimanche)
JOURS_FR = {
    "lundi": 0, "mardi": 1, "mercredi": 2, "jeudi": 3,
    "vendredi": 4, "samedi": 5, "dimanche": 6,
}

ORDINALS_FR = {
    "1er": 1, "1ère": 1, "premier": 1, "première": 1,
    "2e": 2, "2ème": 2, "deuxième": 2,
    "3e": 3, "3ème": 3, "troisième": 3,
    "4e": 4, "4ème": 4, "quatrième": 4,
    "5e": 5, "5ème": 5, "cinquième": 5,
}

WEEKS_AHEAD = 10  # générer les occurrences pour les 10 prochaines semaines


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def fetch_page(slug: str) -> BeautifulSoup | None:
    url = f"{BASE_URL}/fr/audiences/{slug}.html"
    try:
        r = requests.get(url, timeout=15, headers={"Accept-Language": "fr"})
        r.raise_for_status()
        return BeautifulSoup(r.text, "html.parser")
    except Exception as e:
        log(f"  ✗ Erreur {slug}: {e}")
        return None


def parse_time(text: str) -> str:
    """Extrait une heure au format HH:MM depuis du texte."""
    # Gère "9h00", "09:00", "09 :00" (espace avant le séparateur)
    m = re.search(r'\b(\d{1,2})\s*[hH:]\s*(\d{0,2})\b', text)
    if m:
        h = int(m.group(1))
        mi = int(m.group(2)) if m.group(2) else 0
        return f"{h:02d}:{mi:02d}"
    return "09:00"


def parse_jours(text: str) -> list[dict]:
    """
    Parse des expressions comme :
      "lundi"                        → [{weekday:0, nth:[]}]
      "jeudi (1er, 3e)"             → [{weekday:3, nth:[1,3]}]
      "lundi, mercredi"             → [{weekday:0},{weekday:2}]
      "lundi et mardi"              → [{weekday:0},{weekday:1}]
      "chaque jeudi"                → [{weekday:3, nth:[]}]
    Retourne une liste de dicts {weekday: int, nth: list[int]}
    """
    text_lower = text.lower()
    results = []

    for jour_fr, weekday in JOURS_FR.items():
        if jour_fr not in text_lower:
            continue
        # Cherche les ordinaux associés à ce jour
        # Ex: "mardi (2e, 4e)" ou "mardi 2e et 4e"
        pattern = rf'{jour_fr}\s*[\(\[]?([^a-zé]*?)[\)\]]?(?=\s*(?:et|,|$|\d))'
        m = re.search(pattern, text_lower)
        nth = []
        if m:
            ordinals_text = m.group(1)
            for word, n in ORDINALS_FR.items():
                if word in ordinals_text:
                    nth.append(n)
        results.append({"weekday": weekday, "nth": sorted(set(nth))})

    return results


def nth_weekday_of_month(year: int, month: int, weekday: int, n: int) -> date | None:
    """Retourne la nième occurrence d'un jour de semaine dans un mois."""
    first = date(year, month, 1)
    delta = (weekday - first.weekday()) % 7
    first_occ = first + timedelta(days=delta)
    target = first_occ + timedelta(weeks=n - 1)
    if target.month != month:
        return None
    return target


def generate_occurrences(jours: list[dict], horaire: str, today: date) -> list[date]:
    """
    Génère toutes les dates d'audience pour les WEEKS_AHEAD prochaines semaines.
    """
    end = today + timedelta(weeks=WEEKS_AHEAD)
    occurrences = set()
    h, mi = map(int, horaire.split(":"))

    current = today
    while current <= end:
        for j in jours:
            wd = j["weekday"]
            nth = j.get("nth", [])
            if current.weekday() == wd:
                if not nth:
                    # Chaque semaine
                    occurrences.add(current)
                else:
                    # Vérifier si c'est le nth du mois
                    for n in nth:
                        candidate = nth_weekday_of_month(current.year, current.month, wd, n)
                        if candidate == current:
                            occurrences.add(current)
        current += timedelta(days=1)

    return sorted(occurrences)


def parse_table_rows(soup: BeautifulSoup, juridiction: str) -> list[dict]:
    """Extrait les séances depuis un tableau HTML.
    Gère les tableaux mixant <th> et <td> (ex. Justice de Paix Luxembourg)
    et les lignes en rowspan (continuation sans cellule type_affaire).
    """
    entries = []
    tables = soup.find_all("table")

    for table in tables:
        rows = table.find_all("tr")
        for row in rows[1:]:  # skip header row
            # Prend <td> ET <th> pour couvrir les tableaux hybrides
            cells = [c.get_text(" ", strip=True) for c in row.find_all(["td", "th"])]
            if len(cells) < 2:
                continue

            if len(cells) >= 4:
                type_affaire = cells[0]
                jours_txt    = cells[1]
                horaire_txt  = cells[2]
                salle        = cells[3]
            elif len(cells) == 3:
                type_affaire = cells[0]
                jours_txt    = cells[1]
                horaire_txt  = ""
                salle        = cells[2]
                m = re.search(r'\d{1,2}\s*[hH]\s*\d{0,2}', jours_txt)
                if m:
                    horaire_txt = m.group()
            else:
                # 2 cellules : ligne de continuation rowspan [jours_txt, salle]
                # ou ligne simple [type_affaire, jours_txt]
                # Heuristique : si cells[0] contient un jour, c'est une continuation
                if parse_jours(cells[0]):
                    type_affaire = ""
                    jours_txt    = cells[0]
                    horaire_txt  = ""
                    salle        = cells[1]
                    m = re.search(r'\d{1,2}\s*[hH]\s*\d{0,2}', jours_txt)
                    if m:
                        horaire_txt = m.group()
                else:
                    type_affaire = cells[0]
                    jours_txt    = cells[1]
                    horaire_txt  = ""
                    salle        = ""

            horaire = parse_time(horaire_txt or jours_txt)
            jours   = parse_jours(jours_txt)
            if not jours:
                continue

            entries.append({
                "juridiction": juridiction,
                "chambre":     type_affaire,
                "horaire":     horaire,
                "salle":       salle.strip(),
                "jours":       jours,
                "jours_txt":   jours_txt,
            })

    return entries


def parse_text_content(soup: BeautifulSoup, juridiction: str) -> list[dict]:
    """Fallback : extrait les séances depuis du texte non tabulaire."""
    entries = []
    text = soup.get_text(" ", strip=True)

    # Cherche des patterns comme "siège les jeudis à 9h00, salle CR 0.19"
    patterns = [
        r'(?:siège|tient ses audiences?|se réunit)\s+(?:les\s+)?(\w+(?:\s+\w+)?)\s+(?:matin\s+)?(?:à\s+)?(\d{1,2}h\d{0,2})(?:[\s,]+salle\s+([\w\s.]+))?',
        r'(\w+(?:s)?)\s+(?:à\s+)?(\d{1,2}h\d{0,2})(?:[\s,]+salle\s+([\w\s.]+))?',
    ]

    for pattern in patterns:
        for m in re.finditer(pattern, text, re.I):
            jours_txt = m.group(1)
            horaire   = parse_time(m.group(2))
            salle     = (m.group(3) or "").strip() if m.lastindex >= 3 else ""
            jours     = parse_jours(jours_txt)
            if not jours:
                continue
            entries.append({
                "juridiction": juridiction,
                "chambre":     "",
                "horaire":     horaire,
                "salle":       salle,
                "jours":       jours,
                "jours_txt":   jours_txt,
            })
        if entries:
            break

    return entries


def build_ical(events: list[dict]) -> str:
    """Génère un fichier iCal (.ics) depuis la liste d'événements."""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Veille Judiciaire Luxembourg//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:Audiences judiciaires Luxembourg",
        "X-WR-TIMEZONE:Europe/Luxembourg",
    ]
    now_str = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    for ev in events:
        d    = date.fromisoformat(ev["date"])
        h, mi = map(int, ev["horaire"].split(":"))
        start = datetime(d.year, d.month, d.day, h, mi)
        end   = start + timedelta(hours=1)
        title = ev["chambre"] if ev["chambre"] else ev["juridiction"]
        desc  = f"Juridiction : {ev['juridiction']}"
        if ev.get("salle"):
            desc += f"\\nSalle : {ev['salle']}"

        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev['uid']}",
            f"DTSTAMP:{now_str}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{title}",
            f"DESCRIPTION:{desc}",
            f"LOCATION:{ev.get('salle', '')} — {ev['juridiction']}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)


def parse_ul_schedules(soup: BeautifulSoup, juridiction: str) -> list[dict]:
    """Parse les horaires depuis une liste <ul><li>.
    Format : 'Lundi matin à 09 :00 heures Salle 2 – B0.120'
    """
    entries = []
    for ul in soup.find_all("ul"):
        for li in ul.find_all("li"):
            text = li.get_text(" ", strip=True)
            jours = parse_jours(text)
            if not jours:
                continue
            horaire = parse_time(text)
            salle_m = re.search(r'[Ss]alle\s+[\d\w]+\s*[-–]\s*[\w.]+', text)
            salle = salle_m.group(0) if salle_m else ""
            entries.append({
                "juridiction": juridiction,
                "chambre":     "",
                "horaire":     horaire,
                "salle":       salle,
                "jours":       jours,
                "jours_txt":   text,
            })
    return entries


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
        import pdfplumber
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

        # Extraction texte pour recherche
        text = ""
        if has_pdfplumber:
            try:
                import pdfplumber, io
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

    # Lire l'index existant et ajouter les nouvelles entrées (sans doublons)
    index_path = archives_dir / "index.json"
    existing: list[dict] = []
    if index_path.exists():
        try:
            existing = json.loads(index_path.read_text(encoding="utf-8"))
        except Exception:
            existing = []

    # Clé d'unicité : court + chambre + week
    existing_keys = {(r["court"], r["chambre"], r["week"]) for r in existing}
    new_records = [r for r in records if (r["court"], r["chambre"], r["week"]) not in existing_keys]
    all_records = existing + new_records
    # Tri : semaines décroissantes
    all_records.sort(key=lambda x: (x["week"], x["court"], x["chambre"]), reverse=True)

    index_path.write_text(json.dumps(all_records, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"\n✓ archives/index.json → {len(all_records)} entrées ({len(new_records)} nouvelles)")
    return all_records


def main() -> None:
    log("═══════════════════════════════════════════════════════")
    log("  Scraper audiences judiciaires — justice.public.lu")
    log("═══════════════════════════════════════════════════════\n")

    today   = date.today()
    raw     = []   # séances récurrentes brutes
    events  = []   # occurrences calculées avec dates réelles

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
                    "uid":         str(uuid.uuid4()),
                    "date":        occ.isoformat(),
                    "juridiction": entry["juridiction"],
                    "chambre":     entry["chambre"],
                    "horaire":     entry["horaire"],
                    "salle":       entry["salle"],
                    "jours_txt":   entry["jours_txt"],
                })

    events.sort(key=lambda e: (e["date"], e["horaire"]))

    out_dir = Path(__file__).parent

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

    # ── Archives PDF convocations ──────────────────────────────
    log("\n── Téléchargement des convocations PDF ──")
    download_pdf_archive(out_dir)

    log(f"\n═══════════════════════════════════════════════════════")
    log(f"  Terminé : {len(events)} audiences générées ({len(JURIDICTIONS)} juridictions)")
    log(f"═══════════════════════════════════════════════════════")


if __name__ == "__main__":
    main()
