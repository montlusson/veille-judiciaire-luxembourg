-- ═══════════════════════════════════════════════════════════════
-- Watchlist partagée — suivi d'affaires par la rédaction
-- À coller dans : Supabase → SQL Editor → New query → Run
--
-- Remplace le stockage localStorage historique (un suivi par appareil,
-- non partagé) par une liste partagée à toute la rédaction : n'importe
-- quel compte @reporter.lu peut ajouter ou retirer une affaire suivie.
-- Utilisée notamment par la règle de conservation de l'onglet
-- "Audiences passées" : une affaire suivie échappe à la limite d'un an.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS watchlist (
  num        TEXT PRIMARY KEY,
  added_by   TEXT,
  added_at   TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE watchlist ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Reporter read watchlist" ON watchlist;
CREATE POLICY "Reporter read watchlist"
  ON watchlist FOR SELECT
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

DROP POLICY IF EXISTS "Reporter write watchlist" ON watchlist;
CREATE POLICY "Reporter write watchlist"
  ON watchlist FOR INSERT
  WITH CHECK ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

DROP POLICY IF EXISTS "Reporter delete watchlist" ON watchlist;
CREATE POLICY "Reporter delete watchlist"
  ON watchlist FOR DELETE
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

-- Pas de politique UPDATE : une affaire suivie s'ajoute ou se retire,
-- elle ne s'édite pas en place.

-- ── Vérification ───────────────────────────────────────────────
SELECT 'Schéma watchlist créé avec succès ✓' AS status;
