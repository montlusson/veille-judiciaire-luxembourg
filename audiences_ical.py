from __future__ import annotations

"""Génération du calendrier iCal (.ics) depuis la liste d'occurrences d'audiences."""

from datetime import date, datetime, timedelta, timezone


def _ical_escape(text: str) -> str:
    """Échappe les caractères spéciaux selon la spec iCal (RFC 5545)."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


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
    now_str = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for ev in events:
        d    = date.fromisoformat(ev["date"])
        h, mi = map(int, ev["horaire"].split(":"))
        start = datetime(d.year, d.month, d.day, h, mi)
        end   = start + timedelta(hours=1)
        title = ev["chambre"] if ev["chambre"] else ev["juridiction"]
        desc  = f"Juridiction : {ev['juridiction']}"
        if ev.get("salle"):
            desc += f"\\nSalle : {ev['salle']}"
        location = f"{ev.get('salle', '')} — {ev['juridiction']}".strip(" —")

        lines += [
            "BEGIN:VEVENT",
            f"UID:{ev['uid']}",
            f"DTSTAMP:{now_str}",
            f"DTSTART:{start.strftime('%Y%m%dT%H%M%S')}",
            f"DTEND:{end.strftime('%Y%m%dT%H%M%S')}",
            f"SUMMARY:{_ical_escape(title)}",
            f"DESCRIPTION:{_ical_escape(desc)}",
            f"LOCATION:{_ical_escape(location)}",
            "END:VEVENT",
        ]

    lines.append("END:VCALENDAR")
    return "\r\n".join(lines)
