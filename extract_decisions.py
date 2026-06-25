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

import hashlib
import io
import json
import os
import re
import sys
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pdfplumber
import requests

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

# Patterns d'extraction dans le texte des PDF
RE_DATE      = re.compile(r'\b(\d{1,2})[.\s/](\d{1,2})[.\s/](20\d{2})\b')
RE_REF       = re.compile(r'\b(N[°o°]?\s*\d{3,6}[\s/]\d{2,4}|TAL[-\s]\w+[-\s]\d{4}[-\s]\d+)\b', re.I)
RE_AMOUNT    = re.compile(r'(\d[\d\s.,]+)\s*(?:euros?|EUR|€)', re.I)
RE_SOCIETE   = re.compile(r'\b([A-ZÀÂÉÈÊËÎÏÔÙÛÜ][A-Za-zÀ-ÿ\s&\-\'\.]{2,40}(?:S\.A\.|S\.à\s*r\.l\.|S\.à\s*r\.l|SARL|SA|sàrl|GmbH|AG|SAS|SCI|ASBL|a\.s\.b\.l\.))', re.M)
RE_LAWYER    = re.compile(r'(?:Maître|Maı̂tre|Me\.?|avocat(?:e)?(?:\s+\w+)?\s+)\s+([A-ZÀÂÉÈÊËÎÏÔÙÛÜ][A-Za-zÀ-ÿ\-\']{2,30}(?:\s+[A-ZÀÂÉÈÊËÎÏÔÙÛÜ][A-Za-zÀ-ÿ\-\']{1,25}){0,2})', re.M)
RE_RAPPORTEUR = re.compile(r'(?:rapporteur|conseiller\s+rapporteur|juge\s+rapporteur|référendaire)[^\n:]{0,20}:\s*([A-ZÀÂÉÈÊËÎÏÔÙÛÜ][A-Za-zÀ-ÿ\s\-\']{3,40}?)(?=\s*[,\n])', re.I | re.M)
RE_JUDGE     = re.compile(r'(?:président|présidente|juge|conseiller|juge\s+d(?:e\s+)?instruction)[^\n:]{0,15}:\s*([A-ZÀÂÉÈÊËÎÏÔÙÛÜ][A-Za-zÀ-ÿ\s\-\']{3,40}?)(?=\s*[,\n])', re.I | re.M)

OUTPUT_FILE = Path(__file__).parent / "decisions.json"
CACHE_FILE  = Path(__file__).parent / "zip_cache.json"
TIMEOUT     = 30  # secondes par requête HTTP

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
        for res in data.get("resources", []):
            res_url = res.get("url", "")
            title   = (res.get("title", "") + " " + res_url).lower()
            fmt     = res.get("format", "").upper()
            if fmt != "ZIP" and not res_url.lower().endswith(".zip"):
                continue
            for year in (2026, 2025, 2024):
                if str(year) in title and year not in urls:
                    urls[year] = res_url
        _URL_CACHE[slug] = urls
        return urls
    except Exception as e:
        log(f"    ✗ API data.public.lu [{slug}] : {e}")
        _URL_CACHE[slug] = {}
        return {}


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def download_zip(url: str) -> bytes | None:
    """Télécharge un ZIP en mémoire avec progression en temps réel."""
    try:
        r = requests.get(url, timeout=TIMEOUT, stream=True)
        r.raise_for_status()
        total_expected = int(r.headers.get("content-length", 0))
        chunks, total = [], 0
        last_pct = -1
        for chunk in r.iter_content(65536):
            chunks.append(chunk)
            total += len(chunk)
            if total_expected:
                pct = int(total / total_expected * 100)
                if pct >= last_pct + 10:
                    last_pct = pct
                    mb = total / 1024 / 1024
                    print(f"\r    ↓ {mb:.1f} Mo — {pct}%   ", end="", flush=True)
            else:
                mb = total / 1024 / 1024
                if int(mb) > int((total - len(chunk)) / 1024 / 1024):
                    print(f"\r    ↓ {mb:.0f} Mo…   ", end="", flush=True)
        print()  # saut de ligne après la progression
        log(f"    ✓ {total/1024/1024:.1f} Mo téléchargés")
        return b"".join(chunks)
    except Exception as e:
        print()
        log(f"    ✗ Erreur téléchargement : {e}")
        return None


def _fix_joined_words(text: str) -> str:
    """Corrige les mots collés fréquents dans les PDF judiciaires luxembourgeois."""
    # minuscule→Majuscule (ex: "partieDemanderesse" → "partie Demanderesse")
    text = re.sub(r'([a-zàâéèêëîïôùûü])([A-ZÀÂÉÈÊËÎÏÔÙÛÜ])', r'\1 \2', text)
    # chiffre collé à une lettre (ex: "article14" → "article 14", "14euros" → "14 euros")
    text = re.sub(r'([a-zA-ZÀ-ÿ])(\d)', r'\1 \2', text)
    text = re.sub(r'(\d)([a-zA-ZÀ-ÿ])', r'\1 \2', text)
    # ponctuation sans espace suivante (ex: "décision.La" → "décision. La")
    text = re.sub(r'([.!?;:,])([A-ZÀÂÉÈÊËÎÏÔÙÛÜ])', r'\1 \2', text)
    # espaces multiples → simple
    text = re.sub(r'  +', ' ', text)
    return text


def extract_text(pdf_bytes: bytes) -> str:
    """Extrait le texte brut d'un PDF (toutes les pages) avec correction des mots collés."""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            pages = []
            for p in pdf.pages:
                # extract_words restitue mieux l'espacement que extract_text seul
                words = p.extract_words(x_tolerance=2, y_tolerance=3, keep_blank_chars=False)
                if words:
                    # Reconstruction ligne par ligne par proximité verticale
                    lines: dict[int, list[str]] = {}
                    for w in words:
                        row = round(w['top'] / 4)
                        lines.setdefault(row, []).append(w['text'])
                    page_text = '\n'.join(' '.join(lines[r]) for r in sorted(lines))
                else:
                    page_text = p.extract_text() or ''
                pages.append(_fix_joined_words(page_text))
            return "\n".join(pages)
    except Exception:
        return ""


def parse_date(text: str, year_hint: int) -> str | None:
    """Cherche une date dans le texte, préfère celles de l'année indiquée."""
    candidates = RE_DATE.findall(text)
    for day, month, year in candidates:
        if int(year) == year_hint:
            try:
                dt = datetime(int(year), int(month), int(day))
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue
    # Fallback : première date trouvée
    if candidates:
        day, month, year = candidates[0]
        try:
            return datetime(int(year), int(month), int(day)).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return f"{year_hint}-01-01"


def parse_ref(text: str, filename: str) -> str:
    """Extrait la référence de décision depuis le texte ou le nom de fichier."""
    m = RE_REF.search(text[:2000])
    if m:
        return m.group(1).strip()
    # Fallback : nom de fichier sans extension
    stem = Path(filename).stem.replace("_", " ").replace("-", " ")
    return stem[:60]


def parse_amounts(text: str) -> list[int]:
    """Extrait les montants en euros mentionnés dans le texte."""
    amounts = []
    for raw in RE_AMOUNT.findall(text[:5000]):
        cleaned = re.sub(r'[\s]', '', raw).replace(',', '.').replace('\xa0', '')
        try:
            val = int(float(cleaned))
            if 10 < val < 100_000_000:
                amounts.append(val)
        except ValueError:
            pass
    return sorted(set(amounts))[:5]  # max 5 montants


def parse_societes(text: str) -> list[str]:
    """Extrait les noms de sociétés (S.A., S.à r.l., etc.)."""
    found = RE_SOCIETE.findall(text[:6000])
    seen, result = set(), []
    for s in found:
        key = s.strip().lower()
        if key not in seen:
            seen.add(key)
            result.append(s.strip())
    return result[:8]


def make_excerpt(text: str, max_chars: int = 500) -> str:
    """Produit un extrait lisible depuis le texte brut (lignes substantielles)."""
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 40]
    joined = " ".join(lines)
    if len(joined) > max_chars:
        joined = joined[:max_chars].rsplit(" ", 1)[0] + "…"
    return joined


def make_fulltext(text: str, max_chars: int = 12000) -> str:
    """Texte complet pour la recherche — conserve toutes les lignes dont >3 chars."""
    lines = [l.strip() for l in text.splitlines() if len(l.strip()) > 3]
    joined = "\n".join(lines)
    return joined[:max_chars] if len(joined) > max_chars else joined


def parse_lawyers(text: str) -> list[str]:
    """Extrait les noms d'avocats (Maître X, Me X) et de rapporteurs."""
    seen, result = set(), []
    for pattern in (RE_LAWYER, RE_RAPPORTEUR, RE_JUDGE):
        for m in pattern.finditer(text[:15000]):
            name = m.group(1).strip().rstrip(",.")
            key  = name.lower()
            if key not in seen and len(name) > 4:
                seen.add(key)
                result.append(name)
    return result[:20]


def _make_id(jur: str, year: int, ref: str, excerpt: str, fulltext: str = "") -> str:
    """ID stable et unique basé sur le contenu — invariant entre re-extractions."""
    key = f"{jur}::{year}::{ref}::{(excerpt or '')[:80]}::{(fulltext or '')[:120]}"
    return hashlib.sha1(key.encode()).hexdigest()[:16]


def process_pdf(pdf_bytes: bytes, filename: str, source: dict, year: int, zip_url: str = "") -> dict | None:
    """Transforme un PDF en entrée structurée."""
    text = extract_text(pdf_bytes)
    if len(text) < 50:
        return None  # PDF illisible ou vide

    ref      = parse_ref(text, filename)
    date     = parse_date(text, year)
    amounts  = parse_amounts(text)
    societes = parse_societes(text)
    lawyers  = parse_lawyers(text)
    excerpt  = make_excerpt(text)
    fulltext = make_fulltext(text)

    return {
        "id":          _make_id(source["name"], year, ref, excerpt, fulltext),
        "ref":         ref,
        "date":        date,
        "jur":         source["name"],
        "group":       source["group"],
        "type":        source["type"],
        "excerpt":     excerpt,
        "fulltext":    fulltext,
        "entities": {
            "societes": societes,
            "montants": amounts,
            "lawyers":  lawyers,
            "dates":    [date] if date else [],
            "articles": []
        },
        "source_year": year,
    }


def push_to_supabase(decisions: list[dict], generated_at: str) -> None:
    """Envoie les décisions vers Supabase via service_role key."""
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if not url or not key:
        log("  ⚠ Supabase non configuré (SUPABASE_URL / SUPABASE_KEY manquants) — ignoré")
        return

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
    import time
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
            except requests.exceptions.Timeout:
                if attempt < 2:
                    log(f"  ↻ Lot {batch_num} timeout — retry {attempt+2}/3…")
                    time.sleep(5 * (attempt + 1))
                else:
                    errors += 1
                    log(f"  ✗ Lot {batch_num} : timeout après 3 tentatives")

    # Mettre à jour la table meta (timestamp)
    meta_payload = [{"key": "last_generated", "value": generated_at, "updated_at": generated_at}]
    r = requests.post(f"{url}/rest/v1/meta", headers={**headers, "Prefer": "resolution=merge-duplicates"}, json=meta_payload, timeout=10)
    if r.status_code in (200, 201):
        log(f"  ✓ Table meta mise à jour ({generated_at})")
    else:
        log(f"  ✗ Meta : {r.status_code} — {r.text[:100]}")

    if errors == 0:
        log(f"  ✓ Supabase synchronisé — {len(decisions)} décisions")
    else:
        log(f"  ⚠ {errors} lot(s) en erreur — vérifiez les droits service_role")


MAX_WORKERS = 8  # téléchargements simultanés
_log_lock   = threading.Lock()


def _log(msg: str) -> None:
    with _log_lock:
        log(msg)


def _process_task(source: dict, year_int: int, zip_url: str, origin: str) -> tuple[list[dict], dict]:
    """Télécharge un ZIP et extrait ses décisions (exécuté dans un thread)."""
    label = f"{source['name']} [{year_int}]"
    _log(f"  ↓ [{origin}] {label}")
    local = {"zips": 1, "pdfs": 0, "decisions": 0, "errors": 0}
    results: list[dict] = []

    zip_bytes = download_zip(zip_url)
    if not zip_bytes:
        local["errors"] += 1
        return results, local

    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            pdf_names = [n for n in zf.namelist() if n.lower().endswith(".pdf")]
            _log(f"    → {label} : {len(pdf_names)} PDF")
            local["pdfs"] += len(pdf_names)
            for pdf_name in pdf_names:
                try:
                    decision = process_pdf(zf.read(pdf_name), pdf_name, source, year_int, zip_url)
                    if decision:
                        results.append(decision)
                        local["decisions"] += 1
                except Exception as e:
                    _log(f"    ✗ {pdf_name} : {e}")
                    local["errors"] += 1
    except zipfile.BadZipFile:
        _log(f"    ✗ {label} : archive ZIP corrompue")
        local["errors"] += 1

    return results, local


def load_zip_cache() -> dict:
    """Charge le cache des URLs déjà traitées : {cache_key → url}."""
    if CACHE_FILE.exists():
        try:
            return json.loads(CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_zip_cache(cache: dict) -> None:
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def load_existing_decisions() -> list[dict]:
    """Charge les décisions existantes depuis decisions.json."""
    if OUTPUT_FILE.exists():
        try:
            data = json.loads(OUTPUT_FILE.read_text(encoding="utf-8"))
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
            futures = {pool.submit(_process_task, s, yi, url, orig): (s, yi, url)
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

    # Migration des anciens IDs (format "nom-année-fichier") vers le hash stable
    for d in all_decisions:
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

    save_zip_cache(zip_cache)

    log(f"\n═══════════════════════════════════════════════════════")
    log(f"  Terminé : {len(all_decisions)} décisions ({stats['decisions']} nouvelles, "
        f"{stats['skipped']} archives sautées)")
    log(f"  Sources : {stats['sources']} | ZIPs traités : {stats['zips']} | PDF : {stats['pdfs']}")
    if stats['errors']:
        log(f"  Erreurs : {stats['errors']}")
    log(f"  Fichier : {OUTPUT_FILE}")
    log(f"═══════════════════════════════════════════════════════")

    push_to_supabase(all_decisions, output["generated_at"])


if __name__ == "__main__":
    main()
