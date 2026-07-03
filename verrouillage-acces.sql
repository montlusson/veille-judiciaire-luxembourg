-- ═══════════════════════════════════════════════════════════════
-- Verrouillage de l'accès aux données — 3 juillet 2026
-- À coller dans : Supabase → SQL Editor → New query → Run
--
-- Remplace la lecture publique par une lecture réservée aux
-- utilisateurs authentifiés dont l'email se termine par @reporter.lu.
-- Le contrôle du domaine côté client (JS) est contournable ;
-- cette policy s'applique au niveau de la base et ne l'est pas.
-- Les écritures (GitHub Actions via service_role) ne sont pas
-- affectées : service_role contourne RLS.
-- ═══════════════════════════════════════════════════════════════

-- Table decisions : fulltext des décisions
DROP POLICY IF EXISTS "Public read decisions" ON decisions;
DROP POLICY IF EXISTS "Reporter read decisions" ON decisions;
CREATE POLICY "Reporter read decisions"
  ON decisions FOR SELECT
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

-- Table meta : timestamp de dernière extraction
DROP POLICY IF EXISTS "Public read meta" ON meta;
DROP POLICY IF EXISTS "Reporter read meta" ON meta;
CREATE POLICY "Reporter read meta"
  ON meta FOR SELECT
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

-- ── Table files : blobs de données (audiences, archives, ics) ──
-- Remplace les fichiers JSON qui étaient publiés sur GitHub Pages.
CREATE TABLE IF NOT EXISTS files (
  key        TEXT PRIMARY KEY,
  content    JSONB NOT NULL DEFAULT '{}',
  updated_at TIMESTAMPTZ DEFAULT NOW()
);

ALTER TABLE files ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Reporter read files" ON files;
CREATE POLICY "Reporter read files"
  ON files FOR SELECT
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');
DROP POLICY IF EXISTS "Service write files" ON files;
CREATE POLICY "Service write files"
  ON files FOR ALL
  USING (auth.role() = 'service_role');

-- ═══════════════════════════════════════════════════════════════
-- ÉTAPE 2 (recommandée) — Purge des doublons de la table decisions
-- La table contient ~26 000 lignes pour ~10 400 décisions réelles :
-- chaque décision existe sous son ancien ID (texte) ET son ID hash.
-- Reconstruction propre en 2 temps :
--   1. décommenter et exécuter la ligne TRUNCATE ci-dessous
--   2. sur votre Mac : python3 extract_decisions.py --push-supabase
--      (repousse les 10 400 décisions locales avec fulltext complet)
-- En attendant, le module déduplique côté client — rien n'est cassé.
-- ═══════════════════════════════════════════════════════════════
-- TRUNCATE decisions;

-- Vérification : les trois tables doivent lister uniquement
-- "Reporter read …" (SELECT) et "Service write …" (ALL)
SELECT tablename, policyname, cmd
FROM pg_policies
WHERE tablename IN ('decisions', 'meta', 'files')
ORDER BY tablename, policyname;
