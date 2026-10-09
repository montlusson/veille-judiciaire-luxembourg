-- ═══════════════════════════════════════════════════════
-- Purge des données à durée de vie limitée — indépendante de GitHub Actions
-- À coller dans : Supabase (managé ou auto-hébergé) → SQL Editor → New query → Run
-- (idempotent : peut être relancé sans risque)
--
-- Pourquoi : jusqu'ici la purge à 6 mois tournait dans le workflow GitHub keepalive.yml (appel REST
-- avec la clé de service). Sur le Supabase auto-hébergé du NAS, plus de GitHub dans la boucle :
-- la base purge elle-même, chaque nuit, via pg_cron.
--
-- Tables couvertes (rétention 6 mois, obligation RGPD documentée dans le plan NAS) :
--   feuilles_penales   noms de personnes poursuivies — feuilles-penales-schema.sql
--   veille_matches     correspondances prévenus ↔ fiches whoswho — veille-matches-schema.sql
--   rapprochement      pistes de vérification, sauf dossiers à suivi éditorial — rapprochement-schema.sql
-- Une table absente (schéma pas encore installé) est simplement ignorée.
--
-- La lecture est déjà filtrée sur expires_at par les policies RLS : une ligne expirée n'est plus
-- visible même avant la purge. Cette fonction la supprime physiquement.
-- ═══════════════════════════════════════════════════════

CREATE OR REPLACE FUNCTION purge_expirees()
RETURNS TABLE (table_name TEXT, deleted BIGINT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  n BIGINT;
BEGIN
  BEGIN
    DELETE FROM feuilles_penales WHERE expires_at < NOW();
    GET DIAGNOSTICS n = ROW_COUNT;
    table_name := 'feuilles_penales'; deleted := n; RETURN NEXT;
  EXCEPTION WHEN undefined_table THEN NULL;
  END;

  BEGIN
    DELETE FROM veille_matches WHERE expires_at < NOW();
    GET DIAGNOSTICS n = ROW_COUNT;
    table_name := 'veille_matches'; deleted := n; RETURN NEXT;
  EXCEPTION WHEN undefined_table THEN NULL;
  END;

  BEGIN
    DELETE FROM rapprochement WHERE suivi_editorial = FALSE AND expires_at < NOW();
    GET DIAGNOSTICS n = ROW_COUNT;
    table_name := 'rapprochement'; deleted := n; RETURN NEXT;
  EXCEPTION WHEN undefined_table THEN NULL;
  END;
END;
$$;

-- Jamais appelable depuis l'API publique : ni anon, ni un compte connecté. Seul le propriétaire
-- (postgres, utilisé par pg_cron et par l'éditeur SQL) et service_role peuvent l'exécuter.
REVOKE ALL ON FUNCTION purge_expirees() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION purge_expirees() TO service_role;

-- Planification quotidienne à 03h17 (heure du serveur) si l'extension pg_cron est disponible.
-- Sinon : activer pg_cron (Studio → Database → Extensions, ou image Postgres de la pile) puis relancer
-- ce fichier, ou lancer `SELECT * FROM purge_expirees();` depuis une tâche planifiée DSM.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    PERFORM cron.schedule('purge-expirees', '17 3 * * *', 'SELECT * FROM purge_expirees()');
    RAISE NOTICE 'Purge quotidienne planifiée (pg_cron, 03h17).';
  ELSE
    RAISE NOTICE 'pg_cron absent : planifier SELECT * FROM purge_expirees() autrement (tâche DSM).';
  END IF;
END
$$;

-- Vérification à blanc : combien de lignes seraient supprimées maintenant ?
--   SELECT * FROM purge_expirees();   -- exécute réellement la purge (sans risque : seules les lignes expirées)
SELECT 'Fonction purge_expirees() installée ✓' AS status;
