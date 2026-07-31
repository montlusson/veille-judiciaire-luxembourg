from __future__ import annotations

"""Extraction et parsing du texte des décisions PDF."""

import hashlib
import io
import re
from datetime import datetime
from pathlib import Path

import pdfplumber

# Patterns d'extraction dans le texte des PDF
RE_DATE      = re.compile(r'\b(\d{1,2})[.\s/](\d{1,2})[.\s/](20\d{2})\b')
RE_REF       = re.compile(r'\b(N[°o°]?\s*\d{3,6}[\s/]\d{2,4}|TAL[-\s]\w+[-\s]\d{4}[-\s]\d+)\b', re.I)
RE_AMOUNT    = re.compile(r'(\d[\d\s.,]+)\s*(?:euros?|EUR|€)', re.I)
RE_SOCIETE   = re.compile(r'\b([A-ZÀÂÉÈÊËÎÏÔÙÛÜ][A-Za-zÀ-ÿ\s&\-\'\.]{2,40}(?:S\.A\.|S\.à\s*r\.l\.|S\.à\s*r\.l|SARL|SA|sàrl|GmbH|AG|SAS|SCI|ASBL|a\.s\.b\.l\.))', re.M)
RE_LAWYER    = re.compile(r'(?:Maître|Maı̂tre|Me\.?|avocat(?:e)?(?:\s+\w+)?\s+)\s+([A-ZÀÂÉÈÊËÎÏÔÙÛÜ][A-Za-zÀ-ÿ\-\']{2,30}(?:\s+[A-ZÀÂÉÈÊËÎÏÔÙÛÜ][A-Za-zÀ-ÿ\-\']{1,25}){0,2})', re.M)
RE_RAPPORTEUR = re.compile(r'(?:rapporteur|conseiller\s+rapporteur|juge\s+rapporteur|référendaire)[^\n:]{0,20}:\s*([A-ZÀÂÉÈÊËÎÏÔÙÛÜ][A-Za-zÀ-ÿ\s\-\']{3,40}?)(?=\s*[,\n])', re.I | re.M)
RE_JUDGE     = re.compile(r'(?:président|présidente|juge|conseiller|juge\s+d(?:e\s+)?instruction)[^\n:]{0,15}:\s*([A-ZÀÂÉÈÊËÎÏÔÙÛÜ][A-Za-zÀ-ÿ\s\-\']{3,40}?)(?=\s*[,\n])', re.I | re.M)


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
