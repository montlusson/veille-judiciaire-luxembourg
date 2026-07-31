from __future__ import annotations

import os


def get_supabase_credentials() -> tuple[str, str] | None:
    """Lit SUPABASE_URL / SUPABASE_KEY depuis l'environnement.

    Reconstruction robuste : le secret GitHub peut contenir des retours à la
    ligne internes (clé fragmentée, ou URL et clé collées ensemble) qui rendent
    le header HTTP invalide. Une clé Supabase ne contient jamais d'espace :
    on retire les fragments d'URL et on recolle le reste.
    """
    raw_url = os.environ.get("SUPABASE_URL") or ""
    raw_key = os.environ.get("SUPABASE_KEY") or ""
    url_tokens = [t for t in (raw_url.split() + raw_key.split()) if t.lower().startswith("http")]
    url = url_tokens[0].rstrip("/") if url_tokens else ""
    key = "".join(t for t in raw_key.split() if not t.lower().startswith("http"))
    return (url, key) if url and key else None
