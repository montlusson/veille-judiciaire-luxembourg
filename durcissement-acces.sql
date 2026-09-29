-- ═══════════════════════════════════════════════════════════════
-- Durcissement des accès — 29 septembre 2026
-- À coller dans : Supabase → SQL Editor → New query → Run
-- (idempotent : peut être relancé sans risque)
--
-- 1. Domaine strictement ancré : is_reporter() remplace le motif
--    ILIKE '%@reporter.lu' (le % initial acceptait « x@y@reporter.lu »
--    et toute chaîne se terminant par le suffixe).
-- 2. Séparation entre comptes : chaque ligne écrite porte l'e-mail de
--    son auteur (forcé par la base, pas par le client) ; suppression et
--    modification restreintes à l'auteur là où c'est cohérent.
--      - annotations : modification partagée (édition libre voulue),
--        created_by immuable, updated_by = compte connecté,
--        suppression réservée à l'auteur de création.
--      - affaires    : uploaded_by = compte connecté (attribution fiable).
--      - watchlist   : added_by = compte connecté, retrait par l'auteur.
--      - rapprochement / rapprochement_log : insertion et modification
--        réservées à journaliste_email = compte connecté.
-- ═══════════════════════════════════════════════════════════════

-- ── Helpers ─────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION is_reporter()
RETURNS BOOLEAN
LANGUAGE sql STABLE
AS $$
  SELECT lower(coalesce(auth.jwt() ->> 'email', '')) ~ '^[^@[:space:]]+@reporter\.lu$';
$$;

CREATE OR REPLACE FUNCTION jwt_email()
RETURNS TEXT
LANGUAGE sql STABLE
AS $$
  SELECT lower(auth.jwt() ->> 'email');
$$;

-- ── Lecture : decisions, meta, files, archives ──────────────────
DROP POLICY IF EXISTS "Reporter read decisions" ON decisions;
CREATE POLICY "Reporter read decisions" ON decisions FOR SELECT USING (is_reporter());

DROP POLICY IF EXISTS "Reporter read meta" ON meta;
CREATE POLICY "Reporter read meta" ON meta FOR SELECT USING (is_reporter());

DROP POLICY IF EXISTS "Reporter read files" ON files;
CREATE POLICY "Reporter read files" ON files FOR SELECT USING (is_reporter());

DROP POLICY IF EXISTS "Reporter read archives" ON storage.objects;
CREATE POLICY "Reporter read archives" ON storage.objects
  FOR SELECT USING (bucket_id = 'archives' AND is_reporter());

-- ── annotations ─────────────────────────────────────────────────
DROP POLICY IF EXISTS "Reporter read annotations"   ON annotations;
DROP POLICY IF EXISTS "Reporter write annotations"  ON annotations;
DROP POLICY IF EXISTS "Reporter update annotations" ON annotations;
DROP POLICY IF EXISTS "Reporter delete annotations" ON annotations;
DROP POLICY IF EXISTS "Reporter delete own annotations" ON annotations;

CREATE POLICY "Reporter read annotations" ON annotations
  FOR SELECT USING (is_reporter());

CREATE POLICY "Reporter write annotations" ON annotations
  FOR INSERT WITH CHECK (
    is_reporter() AND lower(created_by) = jwt_email()
    AND (updated_by IS NULL OR lower(updated_by) = jwt_email())
  );

CREATE POLICY "Reporter update annotations" ON annotations
  FOR UPDATE USING (is_reporter())
  WITH CHECK (is_reporter() AND (updated_by IS NULL OR lower(updated_by) = jwt_email()));

CREATE POLICY "Reporter delete own annotations" ON annotations
  FOR DELETE USING (is_reporter() AND lower(created_by) = jwt_email());

-- created_by ne peut plus être réécrit après création
CREATE OR REPLACE FUNCTION keep_created_by()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
  NEW.created_by := OLD.created_by;
  RETURN NEW;
END $$;
DROP TRIGGER IF EXISTS annotations_keep_created_by ON annotations;
CREATE TRIGGER annotations_keep_created_by
  BEFORE UPDATE ON annotations FOR EACH ROW EXECUTE FUNCTION keep_created_by();

-- ── affaires ────────────────────────────────────────────────────
DROP POLICY IF EXISTS "Reporter read affaires"   ON affaires;
DROP POLICY IF EXISTS "Reporter write affaires"  ON affaires;
DROP POLICY IF EXISTS "Reporter update affaires" ON affaires;

CREATE POLICY "Reporter read affaires" ON affaires
  FOR SELECT USING (is_reporter());
CREATE POLICY "Reporter write affaires" ON affaires
  FOR INSERT WITH CHECK (is_reporter() AND lower(uploaded_by) = jwt_email());
CREATE POLICY "Reporter update affaires" ON affaires
  FOR UPDATE USING (is_reporter())
  WITH CHECK (is_reporter() AND lower(uploaded_by) = jwt_email());

-- ── watchlist ───────────────────────────────────────────────────
DROP POLICY IF EXISTS "Reporter read watchlist"       ON watchlist;
DROP POLICY IF EXISTS "Reporter write watchlist"      ON watchlist;
DROP POLICY IF EXISTS "Reporter delete watchlist"     ON watchlist;
DROP POLICY IF EXISTS "Reporter delete own watchlist" ON watchlist;

CREATE POLICY "Reporter read watchlist" ON watchlist
  FOR SELECT USING (is_reporter());
CREATE POLICY "Reporter write watchlist" ON watchlist
  FOR INSERT WITH CHECK (is_reporter() AND lower(added_by) = jwt_email());
CREATE POLICY "Reporter delete own watchlist" ON watchlist
  FOR DELETE USING (is_reporter() AND lower(added_by) = jwt_email());

-- ── rapprochement ───────────────────────────────────────────────
DROP POLICY IF EXISTS "Reporter read rapprochement"       ON rapprochement;
DROP POLICY IF EXISTS "Reporter write rapprochement"      ON rapprochement;
DROP POLICY IF EXISTS "Reporter update own rapprochement" ON rapprochement;

CREATE POLICY "Reporter read rapprochement" ON rapprochement
  FOR SELECT USING (is_reporter());
CREATE POLICY "Reporter write rapprochement" ON rapprochement
  FOR INSERT WITH CHECK (is_reporter() AND lower(journaliste_email) = jwt_email());
CREATE POLICY "Reporter update own rapprochement" ON rapprochement
  FOR UPDATE USING (is_reporter() AND lower(journaliste_email) = jwt_email())
  WITH CHECK (is_reporter() AND lower(journaliste_email) = jwt_email());

-- ── rapprochement_log (journal d'audit : ajout seul, aucun UPDATE/DELETE) ──
DROP POLICY IF EXISTS "Reporter read rapprochement_log"  ON rapprochement_log;
DROP POLICY IF EXISTS "Reporter write rapprochement_log" ON rapprochement_log;

CREATE POLICY "Reporter read rapprochement_log" ON rapprochement_log
  FOR SELECT USING (is_reporter());
CREATE POLICY "Reporter write rapprochement_log" ON rapprochement_log
  FOR INSERT WITH CHECK (is_reporter() AND lower(journaliste_email) = jwt_email());

-- ── connexions_log ──────────────────────────────────────────────
DROP POLICY IF EXISTS "Reporter insert own connexion" ON connexions_log;
CREATE POLICY "Reporter insert own connexion" ON connexions_log
  FOR INSERT WITH CHECK (is_reporter() AND lower(email) = jwt_email());

-- ── Vérification : plus aucune policy ne doit contenir « ILIKE '%@ » ──
SELECT tablename, policyname, cmd, qual, with_check
FROM pg_policies
WHERE coalesce(qual, '') ILIKE '%ilike%' OR coalesce(with_check, '') ILIKE '%ilike%';
-- Résultat attendu : 0 ligne.
