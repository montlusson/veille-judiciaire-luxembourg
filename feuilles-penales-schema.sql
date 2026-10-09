-- ═══════════════════════════════════════════════════════
-- Feuilles d'audience pénales et relevés d'appel — table partagée
-- À coller dans : Supabase → SQL Editor → New query → Run
-- (idempotent : peut être relancé sans risque)
--
-- Contenu : le résultat de l'analyse côté navigateur (audiences, salles, prévenus,
-- préventions, jugement attaqué), PAS les PDF. Ce sont des données sur des personnes
-- poursuivies : accès réservé aux comptes @reporter.lu (is_reporter(), défini dans
-- durcissement-acces.sql, recréé ici pour que ce fichier se suffise à lui-même),
-- lecture partagée à toute la rédaction.
--
-- Rétention : 6 mois (expires_at), appliquée à la lecture (une ligne expirée n'est plus
-- visible) ET par purge (workflow keepalive.yml, service_role) — même durée que le module
-- Rapprochement. À revoir lors de la bascule vers le NAS : ce fichier est la seule
-- source de vérité du schéma à migrer.
--
-- Écriture : insertion seule (pas de mise à jour). Un même PDF déposé deux fois (par la
-- même personne ou par une autre) ne crée qu'une ligne — la clé est le SHA-256 du fichier.
-- Chaque ligne porte l'e-mail de son déposant (forcé par la base) et seul celui-ci peut la
-- supprimer avant échéance.
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

CREATE TABLE IF NOT EXISTS feuilles_penales (
  hash           TEXT PRIMARY KEY,                    -- SHA-256 hexadécimal du PDF
  file_name      TEXT NOT NULL,
  jur            TEXT,                                -- "Feuille d'audience" / "Relevé pénal (Cour)"
  chambre        TEXT,
  date_audience  DATE,                                -- première audience du fichier
  source_week    TEXT,                                -- semaine (YYYY-Www) du dépôt
  nb_prevenus    INTEGER NOT NULL DEFAULT 0,
  contenu        JSONB NOT NULL,                      -- { audiences: [...], nb } produit par l'analyse
  uploaded_by    TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  expires_at     TIMESTAMPTZ NOT NULL DEFAULT NOW() + INTERVAL '6 months'
);

CREATE INDEX IF NOT EXISTS feuilles_penales_expires_idx ON feuilles_penales (expires_at);
CREATE INDEX IF NOT EXISTS feuilles_penales_date_idx    ON feuilles_penales (date_audience DESC);

ALTER TABLE feuilles_penales ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Reporter read feuilles_penales" ON feuilles_penales;
CREATE POLICY "Reporter read feuilles_penales" ON feuilles_penales
  FOR SELECT USING (is_reporter() AND expires_at > NOW());

-- Le client ne choisit pas la rétention : une échéance au-delà de 6 mois (+1 jour de marge
-- pour l'écart d'horloge) est refusée.
DROP POLICY IF EXISTS "Reporter write feuilles_penales" ON feuilles_penales;
CREATE POLICY "Reporter write feuilles_penales" ON feuilles_penales
  FOR INSERT WITH CHECK (
    is_reporter()
    AND lower(uploaded_by) = jwt_email()
    AND expires_at <= NOW() + INTERVAL '6 months 1 day'
  );

DROP POLICY IF EXISTS "Reporter delete own feuilles_penales" ON feuilles_penales;
CREATE POLICY "Reporter delete own feuilles_penales" ON feuilles_penales
  FOR DELETE USING (is_reporter() AND lower(uploaded_by) = jwt_email());

-- Purge des lignes expirées : service_role uniquement (workflow planifié keepalive.yml)
DROP POLICY IF EXISTS "Service delete feuilles_penales" ON feuilles_penales;
CREATE POLICY "Service delete feuilles_penales" ON feuilles_penales
  FOR DELETE USING (auth.role() = 'service_role');

SELECT 'Schéma feuilles_penales créé avec succès ✓' AS status;
