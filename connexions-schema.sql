-- ═══════════════════════════════════════════════════════════════
-- Journalisation des connexions — schéma générique, sans données nominatives
-- À coller dans : Supabase → SQL Editor → New query → Run
--
-- Deux niveaux :
--   Niveau 1 (tous les comptes @reporter.lu) : nombre total de connexions
--             uniquement — via une fonction qui ne renvoie qu'un chiffre,
--             aucune ligne individuelle n'est jamais exposée à ce niveau.
--   Niveau 2 (emails listés dans connexions_log_viewers) : détail complet
--             (email + date de chaque connexion).
--
-- IMPORTANT : ce fichier ne contient et ne doit JAMAIS contenir d'adresse
-- email réelle — ce dépôt est public sur GitHub. La table
-- connexions_log_viewers est créée vide ici ; son contenu (les 3 adresses
-- autorisées au détail) doit être inséré séparément, à la main, dans
-- l'éditeur SQL Supabase — jamais via un commit de ce dépôt.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS connexions_log (
  id         BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  email      TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS connexions_log_created_idx ON connexions_log (created_at DESC);

ALTER TABLE connexions_log ENABLE ROW LEVEL SECURITY;

-- Chacun ne peut journaliser que sa propre connexion (email = son propre JWT)
DROP POLICY IF EXISTS "Reporter insert own connexion" ON connexions_log;
CREATE POLICY "Reporter insert own connexion"
  ON connexions_log FOR INSERT
  WITH CHECK ((auth.jwt() ->> 'email') = email AND (auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

-- Écriture/purge réservée à service_role (maintenance éventuelle)
DROP POLICY IF EXISTS "Service manage connexions" ON connexions_log;
CREATE POLICY "Service manage connexions"
  ON connexions_log FOR ALL
  USING (auth.role() = 'service_role');

-- ── Table des emails autorisés à voir le détail (créée vide) ────────────
CREATE TABLE IF NOT EXISTS connexions_log_viewers (
  email TEXT PRIMARY KEY
);
ALTER TABLE connexions_log_viewers ENABLE ROW LEVEL SECURITY;
-- Aucune policy définie ici volontairement : aucun accès direct depuis le
-- client, dans un sens comme dans l'autre. Seules les fonctions
-- SECURITY DEFINER ci-dessous peuvent la consulter (elles contournent RLS
-- en interne car exécutées avec les droits du propriétaire de la fonction).

-- ── Fonctions d'accès contrôlé ───────────────────────────────────────────
CREATE OR REPLACE FUNCTION is_connexion_log_viewer()
RETURNS BOOLEAN
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
  SELECT EXISTS (
    SELECT 1 FROM connexions_log_viewers WHERE email = (auth.jwt() ->> 'email')
  );
$$;
GRANT EXECUTE ON FUNCTION is_connexion_log_viewer() TO authenticated;

CREATE OR REPLACE FUNCTION get_connexions_count()
RETURNS BIGINT
LANGUAGE sql SECURITY DEFINER SET search_path = public
AS $$
  SELECT COUNT(*) FROM connexions_log;
$$;
GRANT EXECUTE ON FUNCTION get_connexions_count() TO authenticated;

-- Détail complet des lignes réservé aux emails inscrits dans connexions_log_viewers
DROP POLICY IF EXISTS "Privileged read connexion detail" ON connexions_log;
CREATE POLICY "Privileged read connexion detail"
  ON connexions_log FOR SELECT
  USING (is_connexion_log_viewer());

-- ── Vérification ─────────────────────────────────────────────────────────
SELECT 'Schéma connexions_log créé avec succès ✓' AS status;
