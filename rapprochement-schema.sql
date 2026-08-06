-- ═══════════════════════════════════════════════════════════════
-- Module Rapprochement d'identité — mode manuel assisté
-- À coller dans : Supabase → SQL Editor → New query → Run
--
-- Ce module ne scrape aucun annuaire professionnel : chaque
-- vérification est faite manuellement par un journaliste sur le
-- site officiel de l'ordre concerné, puis consignée ici.
--
-- Rétention : 6 mois par défaut (expires_at), sauf ligne marquée
-- suivi_editorial = true (dossier confirmé et suivi éditorialement,
-- conservé selon les règles d'archivage rédactionnel habituelles).
-- ═══════════════════════════════════════════════════════════════

-- ── Table des pistes de vérification ────────────────────────────
CREATE TABLE IF NOT EXISTS rapprochement (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  decision_id        TEXT NOT NULL,
  decision_ref       TEXT,
  profession         TEXT NOT NULL,   -- avocats / medecins / notaires / huissiers / oai / oec / reviseurs
  candidat           TEXT,             -- nom du candidat identifié manuellement (facultatif)
  statut             TEXT NOT NULL CHECK (statut IN ('a_verifier','aucune','confirme','ecarte')),
  suivi_editorial    BOOLEAN NOT NULL DEFAULT FALSE,
  journaliste_email  TEXT,
  created_at         TIMESTAMPTZ DEFAULT NOW(),
  expires_at         TIMESTAMPTZ  -- NULL = pas de purge automatique (suivi éditorial actif)
);

CREATE INDEX IF NOT EXISTS rapprochement_decision_idx ON rapprochement (decision_id);
CREATE INDEX IF NOT EXISTS rapprochement_expires_idx  ON rapprochement (expires_at);

ALTER TABLE rapprochement ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Reporter read rapprochement" ON rapprochement;
CREATE POLICY "Reporter read rapprochement"
  ON rapprochement FOR SELECT
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

-- Écriture directe par les journalistes connectés (pas de service_role ici :
-- contrairement aux décisions/audiences, ces lignes sont créées en direct
-- par l'utilisateur authentifié depuis l'app, pas par le pipeline CI).
DROP POLICY IF EXISTS "Reporter write rapprochement" ON rapprochement;
CREATE POLICY "Reporter write rapprochement"
  ON rapprochement FOR INSERT
  WITH CHECK ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

DROP POLICY IF EXISTS "Reporter update own rapprochement" ON rapprochement;
CREATE POLICY "Reporter update own rapprochement"
  ON rapprochement FOR UPDATE
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

-- Purge : service_role uniquement (exécutée par le workflow planifié)
DROP POLICY IF EXISTS "Service delete rapprochement" ON rapprochement;
CREATE POLICY "Service delete rapprochement"
  ON rapprochement FOR DELETE
  USING (auth.role() = 'service_role');

-- ── Journal d'accès / d'actions ─────────────────────────────────
CREATE TABLE IF NOT EXISTS rapprochement_log (
  id                 BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  decision_id        TEXT NOT NULL,
  decision_ref       TEXT,
  action             TEXT NOT NULL,   -- art10_valide / verification_enregistree
  details            JSONB,
  journaliste_email  TEXT,
  created_at         TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS rapprochement_log_decision_idx ON rapprochement_log (decision_id);

ALTER TABLE rapprochement_log ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Reporter read rapprochement_log" ON rapprochement_log;
CREATE POLICY "Reporter read rapprochement_log"
  ON rapprochement_log FOR SELECT
  USING ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

DROP POLICY IF EXISTS "Reporter write rapprochement_log" ON rapprochement_log;
CREATE POLICY "Reporter write rapprochement_log"
  ON rapprochement_log FOR INSERT
  WITH CHECK ((auth.jwt() ->> 'email') ILIKE '%@reporter.lu');

-- Le journal n'est jamais purgé ni modifiable après coup (traçabilité).

-- ── Vérification ───────────────────────────────────────────────
SELECT 'Schéma rapprochement créé avec succès ✓' AS status;
