-- ═══════════════════════════════════════════════════════════════
-- Affaires en cours — table partagée alimentée par les dépôts PDF
-- À coller dans : Supabase → SQL Editor → New query → Run
--
-- Remplace le pipeline automatisé de scraping des PDF de convocation
-- (juridiquement risqué, cf. audiences_pdf.py retiré du CI) par un dépôt
-- volontaire : un journaliste télécharge lui-même le PDF de convocation
-- publié par le greffe, le dépose dans l'app (onglet Audiences), le texte
-- est extrait et analysé côté client (parseConvocationText) puis les
-- affaires qui en résultent sont poussées ici, visibles par toute la
-- rédaction @reporter.lu quel que soit qui a déposé le PDF.
--
-- Upsert par numéro d'affaire : le dernier dépôt écrase le stade
-- précédent (cohérent avec la logique "une affaire qui disparaît du
-- rôle a vraisemblablement été jugée").
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS affaires (
  num          TEXT PRIMARY KEY,
  juridiction  TEXT,       -- "Cour adm." / "Trib. 1re ch." … (même format que renderAffaireRow côté app)
  matiere      TEXT,
  defendeur    TEXT,
  avocat       TEXT,
  stade        TEXT,       -- "Mise en état" / "Plaidoirie" / "Délibéré"
  source_week  TEXT,       -- semaine (YYYY-Www) de la convocation déposée
  uploaded_by  TEXT,
  date_audience DATE,      -- date d'audience extraite du PDF (onglet "Audiences passées")
  updated_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS affaires_juridiction_idx ON affaires (juridiction);
CREATE INDEX IF NOT EXISTS affaires_week_idx        ON affaires (source_week);

ALTER TABLE affaires ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Reporter read affaires" ON affaires;
CREATE POLICY "Reporter read affaires"
  ON affaires FOR SELECT
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

DROP POLICY IF EXISTS "Reporter write affaires" ON affaires;
CREATE POLICY "Reporter write affaires"
  ON affaires FOR INSERT
  WITH CHECK ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

DROP POLICY IF EXISTS "Reporter update affaires" ON affaires;
CREATE POLICY "Reporter update affaires"
  ON affaires FOR UPDATE
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

-- Pas de politique DELETE : les affaires sont remplacées par upsert
-- (dépôt suivant), jamais supprimées manuellement depuis l'app.

-- ═══════════════════════════════════════════════════════════════
-- Ajout colonne date_audience (refonte onglet "Audiences & agenda") —
-- à exécuter si la table `affaires` existe déjà (installation antérieure
-- à cet ajout). Sans effet si la table vient d'être créée ci-dessus
-- (colonne déjà présente). Supabase → SQL Editor → New query → Run.
-- ═══════════════════════════════════════════════════════════════
ALTER TABLE affaires ADD COLUMN IF NOT EXISTS date_audience DATE;
CREATE INDEX IF NOT EXISTS affaires_date_audience_idx ON affaires (date_audience);

-- ── Vérification ───────────────────────────────────────────────
SELECT 'Schéma affaires créé avec succès ✓' AS status;
