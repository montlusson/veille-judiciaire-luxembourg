from __future__ import annotations

"""Sources officielles (data.public.lu) et résolution des URLs de téléchargement."""

import requests

from lib.logutil import log

# ── Sources officielles ────────────────────────────────────────────────────────
SOURCES = [
    # Cour de Cassation
    {"group": "Cour de Cassation", "name": "Cour de Cassation", "type": "Civil",
     "zip2026": "https://download.data.public.lu/resources/cour-de-cassation-1/20260608-114830/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/cour-de-cassation-1/20260608-114829/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/cour-de-cassation-1/20260608-114828/2024.zip"},

    # Cour supérieure de justice
    {"group": "Cour supérieure de justice", "name": "CSJ – 1re Chambre", "type": "Civil",
     "zip2026": "https://download.data.public.lu/resources/cour-superieure-de-justice-1e-chambre-1/20260608-114956/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/cour-superieure-de-justice-1e-chambre-1/20260608-114955/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/cour-superieure-de-justice-1e-chambre-1/20260608-114954/2024.zip"},
    {"group": "Cour supérieure de justice", "name": "CSJ – Chambre du Conseil", "type": "Chambre du Conseil",
     "zip2026": "https://download.data.public.lu/resources/cour-superieure-de-justice-chambre-du-conseil-2/20260608-114907/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/cour-superieure-de-justice-chambre-du-conseil-2/20260608-114906/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/cour-superieure-de-justice-chambre-du-conseil-2/20260608-114905/2024.zip"},
    {"group": "Cour supérieure de justice", "name": "CSJ – Chambre de l'application des peines", "type": "Pénal",
     "zip2026": "https://download.data.public.lu/resources/cour-superieure-de-justice-chambre-de-lapplication-des-peines-1/20260608-115848/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/cour-superieure-de-justice-chambre-de-lapplication-des-peines-1/20260608-115847/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/cour-superieure-de-justice-chambre-de-lapplication-des-peines-1/20260614-230303/2024.zip"},
    {"group": "Cour supérieure de justice", "name": "CSJ – Chambre des vacations", "type": "Civil",
     "zip2026": "https://download.data.public.lu/resources/cour-superieure-de-justice-chambre-des-vacations-1/20260608-115902/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/cour-superieure-de-justice-chambre-des-vacations-1/20260608-115901/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/cour-superieure-de-justice-chambre-des-vacations-1/20260608-115900/2024.zip"},
    {"group": "Cour supérieure de justice", "name": "CSJ – Chambre de la Jeunesse", "type": "Jeunesse",
     "zip2026": None, "zip2025": None, "zip2024": None},

    # Justice de Paix – Diekirch
    {"group": "Justice de Paix Diekirch", "name": "JP Diekirch – Bail", "type": "Bail",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-diekirch-bail/20260608-115947/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-diekirch-bail/20260608-115946/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-diekirch-bail/20260608-115945/2024.zip"},
    {"group": "Justice de Paix Diekirch", "name": "JP Diekirch – Civil", "type": "Civil",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-diekirch-civil/20260608-115958/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-diekirch-civil/20260608-115957/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-diekirch-civil/20260608-115956/2024.zip"},
    {"group": "Justice de Paix Diekirch", "name": "JP Diekirch – IPA-RPL", "type": "IPA-RPL",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-diekirch-ipa-rpl/20260608-120016/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-diekirch-ipa-rpl/20260608-120015/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-diekirch-ipa-rpl/20260608-120014/2024.zip"},
    {"group": "Justice de Paix Diekirch", "name": "JP Diekirch – Police", "type": "Police",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-diekirch-police/20260608-120027/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-diekirch-police/20260608-120026/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-diekirch-police/20260608-120025/2024.zip"},
    {"group": "Justice de Paix Diekirch", "name": "JP Diekirch – Saisie-Cession", "type": "Saisie-Cession",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-diekrich-saisie-cession/20260608-120038/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-diekrich-saisie-cession/20260608-120037/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-diekrich-saisie-cession/20260608-120036/2024.zip"},
    {"group": "Justice de Paix Diekirch", "name": "JP Diekirch – Surendettement", "type": "Surendettement",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-diekirch-surendettement/20260608-120047/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-diekirch-surendettement/20260608-120046/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-diekirch-surendettement/20260608-120045/2024.zip"},
    {"group": "Justice de Paix Diekirch", "name": "JP Diekirch – Travail", "type": "Travail",
     "zip2026": None, "zip2025": None, "zip2024": None},

    # Justice de Paix – Luxembourg
    {"group": "Justice de Paix Luxembourg", "name": "JP Luxembourg – Bail", "type": "Bail",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-bail-1/20260608-120317/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-bail-1/20260608-120316/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-bail-1/20260608-120315/2024.zip"},
    {"group": "Justice de Paix Luxembourg", "name": "JP Luxembourg – CAS", "type": "Civil",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-cas/20260608-120324/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-cas/20260608-120323/2025.zip",
     "zip2024": None},
    {"group": "Justice de Paix Luxembourg", "name": "JP Luxembourg – Civil", "type": "Civil",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-civil-1/20260608-120351/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-civil-1/20260608-120350/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-civil-1/20260608-120349/2024.zip"},
    {"group": "Justice de Paix Luxembourg", "name": "JP Luxembourg – IPA-RPL", "type": "IPA-RPL",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-ipa-rpl-1/20260608-120418/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-ipa-rpl-1/20260608-120417/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-ipa-rpl-1/20260608-120416/2024.zip"},
    {"group": "Justice de Paix Luxembourg", "name": "JP Luxembourg – Police", "type": "Police",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-police-1/20260608-120432/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-police-1/20260608-120431/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-police-1/20260608-120430/2024.zip"},
    {"group": "Justice de Paix Luxembourg", "name": "JP Luxembourg – Saisie-Cession", "type": "Saisie-Cession",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-saisie-cession-1/20260608-120448/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-saisie-cession-1/20260608-120447/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-saisie-cession-1/20260608-120446/2024.zip"},
    {"group": "Justice de Paix Luxembourg", "name": "JP Luxembourg – Surendettement", "type": "Surendettement",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-surendettement-1/20260608-120458/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-surendettement-1/20260608-120457/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-surendettement-1/20260608-120456/2024.zip"},
    {"group": "Justice de Paix Luxembourg", "name": "JP Luxembourg – Travail", "type": "Travail",
     "zip2026": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-travail-1/20260608-120529/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/justice-de-paix-luxembourg-travail-1/20260608-120528/2025.zip",
     "zip2024": None},

    # Tribunal d'arrondissement de Luxembourg
    {"group": "Tribunal d'arrondissement de Luxembourg", "name": "TAL – Civil Ch. 01", "type": "Civil",
     "zip2026": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-01-1/20260608-120906/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-01-1/20260608-120905/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-01-1/20260608-120904/2024.zip"},
    {"group": "Tribunal d'arrondissement de Luxembourg", "name": "TAL – Civil Ch. 03", "type": "Civil",
     "zip2026": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-03-1/20260608-120955/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-03-1/20260608-120954/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-03-1/20260608-120953/2024.zip"},
    {"group": "Tribunal d'arrondissement de Luxembourg", "name": "TAL – Civil Ch. 04", "type": "Civil",
     "zip2026": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-04-1/20260608-121023/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-04-1/20260608-121022/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-04-1/20260608-121021/2024.zip"},
    {"group": "Tribunal d'arrondissement de Luxembourg", "name": "TAL – Civil Ch. 08", "type": "Civil",
     "zip2026": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-08-1/20260608-121111/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-08-1/20260608-121110/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-civil-chambre-08-1/20260608-121109/2024.zip"},
    {"group": "Tribunal d'arrondissement de Luxembourg", "name": "TAL – Pénal Ch. 9 correctionnelle", "type": "Pénal correctionnelle",
     "zip2026": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-9-correctionnelle/20260614-230816/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-9-correctionnelle/20260614-230815/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-9-correctionnelle/20260608-121734/2024.zip"},
    {"group": "Tribunal d'arrondissement de Luxembourg", "name": "TAL – Pénal Ch. 12 correctionnelle", "type": "Pénal correctionnelle",
     "zip2026": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-12-correctionnelle/20260608-121832/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-12-correctionnelle/20260608-121831/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-12-correctionnelle/20260608-121830/2024.zip"},
    {"group": "Tribunal d'arrondissement de Luxembourg", "name": "TAL – Pénal Ch. 12 criminelle", "type": "Pénal criminelle",
     "zip2026": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-12-criminelle/20260608-121842/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-12-criminelle/20260608-121841/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-12-criminelle/20260608-121840/2024.zip"},
    {"group": "Tribunal d'arrondissement de Luxembourg", "name": "TAL – Pénal Ch. 13 correctionnelle", "type": "Pénal correctionnelle",
     "zip2026": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-13-correctionnelle/20260608-121912/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-13-correctionnelle/20260608-121911/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-13-correctionnelle/20260608-121910/2024.zip"},
    {"group": "Tribunal d'arrondissement de Luxembourg", "name": "TAL – Pénal Ch. 13 criminelle", "type": "Pénal criminelle",
     "zip2026": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-13-criminelle/20260608-121931/2026.zip",
     "zip2025": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-13-criminelle/20260608-121930/2025.zip",
     "zip2024": "https://download.data.public.lu/resources/tribunal-darrondissement-luxembourg-penal-chambre-13-criminelle/20260608-121929/2024.zip"},
]

YEARS = ["zip2026", "zip2025", "zip2024"]

# Cache des URLs résolues via l'API data.public.lu (évite les hits répétés)
_URL_CACHE: dict[str, dict[int, str]] = {}


def get_slug(source: dict) -> str | None:
    """Extrait le slug du dataset depuis l'une des URLs codées en dur."""
    for key in ("zip2026", "zip2025", "zip2024"):
        url = source.get(key)
        if url:
            try:
                return url.split("/resources/")[1].split("/")[0]
            except IndexError:
                pass
    return None


def resolve_zip_urls(slug: str) -> dict[int, str]:
    """Interroge l'API data.public.lu pour obtenir les URLs de téléchargement courantes."""
    if slug in _URL_CACHE:
        return _URL_CACHE[slug]

    api_url = f"https://data.public.lu/api/1/datasets/{slug}/"
    try:
        r = requests.get(api_url, timeout=15)
        r.raise_for_status()
        data = r.json()
        urls: dict[int, str] = {}
        zip_resources = []
        for res in data.get("resources", []):
            res_url = res.get("url", "")
            fmt     = res.get("format", "").upper()
            if fmt != "ZIP" and not res_url.lower().endswith(".zip"):
                continue
            zip_resources.append(res)
        # Passe 1 : nom de fichier exact ("…/2025.zip") — fiable.
        # Le titre/URL contient aussi le timestamp d'upload (ex. 20260608)
        # qui matcherait "2026" par sous-chaîne et fausserait l'année.
        for res in zip_resources:
            res_url  = res.get("url", "")
            basename = res_url.rsplit("/", 1)[-1].lower()
            for year in (2026, 2025, 2024):
                if year not in urls and basename == f"{year}.zip":
                    urls[year] = res_url
        # Passe 2 (fallback) : année dans le titre seul (jamais l'URL)
        for res in zip_resources:
            res_url = res.get("url", "")
            title   = res.get("title", "").lower()
            for year in (2026, 2025, 2024):
                if year not in urls and str(year) in title:
                    urls[year] = res_url
        _URL_CACHE[slug] = urls
        return urls
    except Exception as e:
        log(f"    ✗ API data.public.lu [{slug}] : {e}")
        _URL_CACHE[slug] = {}
        return {}
