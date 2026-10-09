-- ═══════════════════════════════════════════════════════
-- Correspondances prévenus ↔ fiches whoswho-lu — pont entre Veille judiciaire et whoswho-lu
-- À coller dans : Supabase → SQL Editor → New query → Run
-- (idempotent : peut être relancé sans risque)
-- À exécuter APRÈS feuilles-penales-schema.sql (qui définit is_reporter() / jwt_email()).
--
-- Rôle : Veille (navigateur du journaliste) compare les noms de prévenus des feuilles
-- d'audience à l'annuaire whoswho-lu et dépose ici UNE LIGNE PAR CORRESPONDANCE POSSIBLE.
-- whoswho-lu les lit et affiche une notification « à vérifier » sur la fiche : un journaliste
-- confirme (l'affaire entre dans « Affaires judiciaires liées ») ou écarte (homonyme).
-- Une ligne ne prouve pas que la personne est la bonne : même nom + même prénom ≠ même
-- personne. Rien n'est rattaché à une fiche sans confirmation humaine.
--
-- Accès : comptes @reporter.lu, lecture partagée. Rétention 6 mois, comme feuilles_penales
-- (lecture filtrée sur expires_at + purge par keepalive.yml). La décision (confirmée /
-- écartée) vit côté whoswho-lu, dans la fiche elle-même, pas ici.
-- ═══════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS veille_matches (
  id             TEXT PRIMARY KEY,            -- fiche_id|hash du PDF|date|nom normalisé du prévenu
  fiche_id       TEXT NOT NULL,               -- id de la fiche whoswho-lu (personnes.json / D1)
  fiche_nom      TEXT,
  prevenu_nom    TEXT NOT NULL,               -- tel qu'écrit dans la feuille ("NOM Prénom")
  exact          BOOLEAN NOT NULL DEFAULT FALSE,   -- TRUE = prénom(s) identiques, FALSE = prénom proche
  feuille_hash   TEXT NOT NULL,               -- SHA-256 du PDF (clé de feuilles_penales.hash)
  file_name      TEXT,
  date_audience  DATE,
  heure          TEXT,
  salle          TEXT,
  chambre        TEXT,
  juridiction    TEXT,
  preventions    TEXT,
  jugement       TEXT,
  created_by     TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at     TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '6 months'
);

CREATE INDEX IF NOT EXISTS veille_matches_fiche_idx   ON veille_matches (fiche_id);
CREATE INDEX IF NOT EXISTS veille_matches_expires_idx ON veille_matches (expires_at);

ALTER TABLE veille_matches ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Reporter read veille_matches" ON veille_matches;
CREATE POLICY "Reporter read veille_matches" ON veille_matches
  FOR SELECT USING (is_reporter() AND expires_at > NOW());

DROP POLICY IF EXISTS "Reporter write veille_matches" ON veille_matches;
CREATE POLICY "Reporter write veille_matches" ON veille_matches
  FOR INSERT WITH CHECK (
    is_reporter()
    AND lower(created_by) = jwt_email()
    AND expires_at <= NOW() + INTERVAL '6 months 1 day'
  );

DROP POLICY IF EXISTS "Reporter delete own veille_matches" ON veille_matches;
CREATE POLICY "Reporter delete own veille_matches" ON veille_matches
  FOR DELETE USING (is_reporter() AND lower(created_by) = jwt_email());

DROP POLICY IF EXISTS "Service delete veille_matches" ON veille_matches;
CREATE POLICY "Service delete veille_matches" ON veille_matches
  FOR DELETE USING (auth.role() = 'service_role');

SELECT 'Schéma veille_matches créé avec succès ✓' AS status;
