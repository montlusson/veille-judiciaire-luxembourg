-- ═══════════════════════════════════════════════════════════════
-- Annotations partagées — onglet Recherche & entités
-- À coller dans : Supabase → SQL Editor → New query → Run
--
-- Remplace le stockage localStorage historique (une annotation par
-- appareil, non partagée) par une table partagée à toute la rédaction :
-- n'importe quel compte @reporter.lu peut créer ou modifier une
-- annotation existante (édition libre), l'auteur de création et le
-- dernier auteur de modification sont conservés pour attribution.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS annotations (
  decision_id  TEXT PRIMARY KEY,
  parties      JSONB NOT NULL DEFAULT '[]',
  tags         JSONB NOT NULL DEFAULT '[]',
  notes        TEXT DEFAULT '',
  created_by   TEXT NOT NULL,
  updated_by   TEXT,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE annotations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Reporter read annotations" ON annotations;
CREATE POLICY "Reporter read annotations"
  ON annotations FOR SELECT
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

-- Édition libre : n'importe quel compte @reporter.lu peut créer ou
-- modifier une annotation existante (pas de restriction "auteur uniquement").
DROP POLICY IF EXISTS "Reporter write annotations" ON annotations;
CREATE POLICY "Reporter write annotations"
  ON annotations FOR INSERT
  WITH CHECK ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

DROP POLICY IF EXISTS "Reporter update annotations" ON annotations;
CREATE POLICY "Reporter update annotations"
  ON annotations FOR UPDATE
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

DROP POLICY IF EXISTS "Reporter delete annotations" ON annotations;
CREATE POLICY "Reporter delete annotations"
  ON annotations FOR DELETE
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

-- ── Vérification ───────────────────────────────────────────────
SELECT 'Schéma annotations créé avec succès ✓' AS status;
