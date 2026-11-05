-- ═══════════════════════════════════════════════════════
-- Décisions des juridictions administratives — table partagée, alimentée à la main
-- À coller dans : Supabase → SQL Editor → New query → Run
-- (idempotent : peut être relancé sans risque)
--
-- Pourquoi une table à part : ces décisions ne sont PAS dans les données ouvertes de
-- data.public.lu (jeux « Administration judiciaire »), et ja.public.lu interdit tout robot
-- (robots.txt : Disallow: /). Elles entrent donc par collage dans le module (Publications
-- récentes → « Ajouter des décisions administratives »), jamais par extraction automatique.
--
-- Clé : le numéro de rôle (un PDF = un numéro, ex. 49856 ou 55868R). Coller deux fois le
-- même numéro complète la ligne au lieu d'en créer une seconde.
--
-- Données : décisions publiques et pseudonymisées (« Monsieur (A) »). Lecture et écriture
-- réservées aux comptes @reporter.lu (is_reporter(), recréé ici pour que ce fichier se
-- suffise à lui-même). Les contraintes CHECK refusent tout contenu mal formé : le module
-- affiche ces champs dans des pages lues par toute la rédaction (défense en profondeur
-- contre le XSS stocké, même principe que feuilles_penales).
-- ═══════════════════════════════════════════════════════
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

CREATE TABLE IF NOT EXISTS decisions_admin (
  role_num      TEXT PRIMARY KEY,                 -- numéro de rôle : 49856, 55868R, 54701C…
  ecli          TEXT,                             -- ECLI:LU:TADM:2026:49856
  juridiction   TEXT NOT NULL DEFAULT 'Tribunal administratif',
  instance      TEXT,                             -- Tribunal / Référé / Cour
  chambre       TEXT,                             -- numéro de chambre
  contentieux   TEXT,                             -- « Administratif »…
  date_audience DATE,
  resume        TEXT,                             -- recours formé par…, contre…
  url           TEXT,                             -- PDF sur ja.public.lu, si collé
  added_by      TEXT NOT NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  CONSTRAINT decisions_admin_role_forme   CHECK (role_num ~ '^[0-9]{4,6}[A-Z]{0,2}$'),
  CONSTRAINT decisions_admin_ecli_forme   CHECK (ecli IS NULL OR ecli ~ '^ECLI:LU:[A-Z]{2,8}:[0-9]{4}:[A-Za-z0-9]{1,20}$'),
  CONSTRAINT decisions_admin_juridiction  CHECK (juridiction IN ('Tribunal administratif', 'Cour administrative')),
  CONSTRAINT decisions_admin_instance     CHECK (instance IS NULL OR instance IN ('Tribunal', 'Référé', 'Cour')),
  CONSTRAINT decisions_admin_chambre      CHECK (chambre IS NULL OR chambre ~ '^[0-9]{1,2}$'),
  CONSTRAINT decisions_admin_contentieux  CHECK (contentieux IS NULL OR length(contentieux) <= 60),
  CONSTRAINT decisions_admin_resume       CHECK (resume IS NULL OR length(resume) <= 1500),
  CONSTRAINT decisions_admin_url_forme    CHECK (url IS NULL OR url ~ '^https://ja\.public\.lu/[A-Za-z0-9_./-]{1,150}\.pdf$')
);

CREATE INDEX IF NOT EXISTS decisions_admin_date_idx ON decisions_admin (date_audience DESC NULLS LAST);

ALTER TABLE decisions_admin ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Reporter read decisions_admin" ON decisions_admin;
CREATE POLICY "Reporter read decisions_admin" ON decisions_admin
  FOR SELECT USING (is_reporter());

DROP POLICY IF EXISTS "Reporter insert decisions_admin" ON decisions_admin;
CREATE POLICY "Reporter insert decisions_admin" ON decisions_admin
  FOR INSERT WITH CHECK (is_reporter() AND lower(added_by) = jwt_email());

-- Collection partagée (comme la watchlist) : n'importe quel compte de la rédaction peut
-- compléter une ligne. Les CHECK ci-dessus s'appliquent aussi aux mises à jour.
DROP POLICY IF EXISTS "Reporter update decisions_admin" ON decisions_admin;
CREATE POLICY "Reporter update decisions_admin" ON decisions_admin
  FOR UPDATE USING (is_reporter()) WITH CHECK (is_reporter());

-- Seul l'auteur d'une ligne peut la supprimer.
DROP POLICY IF EXISTS "Reporter delete own decisions_admin" ON decisions_admin;
CREATE POLICY "Reporter delete own decisions_admin" ON decisions_admin
  FOR DELETE USING (is_reporter() AND lower(added_by) = jwt_email());

CREATE OR REPLACE FUNCTION decisions_admin_touch()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$;
DROP TRIGGER IF EXISTS decisions_admin_updated_at ON decisions_admin;
CREATE TRIGGER decisions_admin_updated_at
  BEFORE UPDATE ON decisions_admin
  FOR EACH ROW EXECUTE FUNCTION decisions_admin_touch();

SELECT 'Schéma decisions_admin créé avec succès ✓' AS status;
