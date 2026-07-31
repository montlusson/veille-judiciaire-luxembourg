from __future__ import annotations

"""Récupération des pages d'audiences et parsing des horaires/jours récurrents."""

import re
from datetime import date, timedelta

import requests
from bs4 import BeautifulSoup

from lib.logutil import log

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
