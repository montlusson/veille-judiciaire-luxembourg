-- ═══════════════════════════════════════════════════════════════
-- Veille judiciaire Luxembourg — Schéma Supabase
-- À coller dans : Supabase → SQL Editor → New query → Run
-- ═══════════════════════════════════════════════════════════════

-- Table principale des décisions
CREATE TABLE IF NOT EXISTS decisions (
  id           TEXT PRIMARY KEY,
  ref          TEXT NOT NULL,
  date         TEXT,
  jur          TEXT,
  "group"      TEXT,
  type         TEXT,
  excerpt      TEXT,
  fulltext     TEXT,
  entities     JSONB DEFAULT '{}',
  source_year  INTEGER,
  archived     BOOLEAN DEFAULT FALSE,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

-- Index sur date (tri par défaut)
CREATE INDEX IF NOT EXISTS decisions_date_idx  ON decisions (date DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS decisions_jur_idx   ON decisions (jur);
CREATE INDEX IF NOT EXISTS decisions_year_idx  ON decisions (source_year);

-- Recherche plein texte (ref + jur + type + excerpt — fulltext chargé à la demande)
ALTER TABLE decisions ADD COLUMN IF NOT EXISTS fts tsvector
  GENERATED ALWAYS AS (
    to_tsvector('french',
      COALESCE(ref,     '') || ' ' ||
      COALESCE(jur,     '') || ' ' ||
      COALESCE(type,    '') || ' ' ||
      COALESCE(excerpt, '') || ' ' ||
      COALESCE(LEFT(fulltext, 20000), '')
    )
  ) STORED;

CREATE INDEX IF NOT EXISTS decisions_fts_idx ON decisions USING GIN(fts);

-- Mise à jour automatique du champ updated_at
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;

DROP TRIGGER IF EXISTS decisions_updated_at ON decisions;
CREATE TRIGGER decisions_updated_at
  BEFORE UPDATE ON decisions
  FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ── Sécurité (Row Level Security) ──────────────────────────────
ALTER TABLE decisions ENABLE ROW LEVEL SECURITY;

-- Lecture publique (les décisions judiciaires sont publiques)
DROP POLICY IF EXISTS "Public read decisions" ON decisions;
CREATE POLICY "Public read decisions"
  ON decisions FOR SELECT
  USING (true);

-- Écriture réservée au service_role (GitHub Actions)
DROP POLICY IF EXISTS "Service write decisions" ON decisions;
CREATE POLICY "Service write decisions"
  ON decisions FOR ALL
  USING (auth.role() = 'service_role');

-- ── Table métadonnées (timestamp de la dernière extraction) ────
CREATE TABLE IF NOT EXISTS meta (
  key   TEXT PRIMARY KEY,
  value TEXT,
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE meta ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Public read meta" ON meta FOR SELECT USING (true);
CREATE POLICY "Service write meta" ON meta FOR ALL USING (auth.role() = 'service_role');

-- ── Vérification ───────────────────────────────────────────────
-- Après exécution, vous devriez voir :
--   decisions : 0 lignes (elles arriveront via GitHub Actions)
--   meta      : 0 lignes
SELECT 'Schéma créé avec succès ✓' AS status;
