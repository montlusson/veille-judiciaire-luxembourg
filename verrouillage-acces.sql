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

-- Vérification : les deux tables doivent lister uniquement
-- "Reporter read …" (SELECT) et "Service write …" (ALL)
SELECT tablename, policyname, cmd
FROM pg_policies
WHERE tablename IN ('decisions', 'meta')
ORDER BY tablename, policyname;
