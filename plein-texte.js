/* ===================== RECHERCHE PLEIN TEXTE (index Postgres) =====================
   Le module charge les décisions SANS leur texte (extrait de 200 caractères) : la
   recherche locale ne voit donc que la référence, la juridiction, le type, cet extrait,
   les entités et les annotations. Ce fichier interroge en plus l'index plein texte de
   Supabase (colonne `fts` de la table `decisions`, 20 000 premiers caractères du texte,
   config « french ») et ne renvoie que des identifiants : le texte reste sur le serveur.

   Deux usages, tous deux « en plus » du filtrage local (jamais à sa place) :
   - la recherche de l'écran « Recherche & entités » ;
   - les mots-clés du Radar et les pastilles de « Publications récentes ».

   Un mot-clé peut contenir plusieurs variantes séparées par « | » (utilisé par les thèmes
   du Radar) : elles sont combinées en OU. Hors ligne ou sans Supabase, tout retombe sur la
   correspondance locale — ftsIds() renvoie alors null. */
(function(){
  'use strict';

  var PAGE = 1000;          /* plafond PostgREST par requête */
  var MAX_ROWS = 5000;      /* garde-fou : au-delà, la requête est trop large pour être utile */
  var TTL = 5 * 60 * 1000;
  var _cache = {};

  /* « a | b » → "a" or "b" (syntaxe websearch) ; une saisie simple est transmise telle quelle. */
  function toQuery(kw){
    var parts = String(kw).split('|').map(function(s){ return s.trim(); }).filter(Boolean);
    if(parts.length > 1) return parts.map(function(p){ return '"' + p.replace(/"/g, '') + '"'; }).join(' or ');
    return parts[0] || '';
  }

  /* Ensemble des identifiants dont le texte correspond à kw (et arrivés depuis sinceISO si
     fourni), ou null si l'index n'est pas interrogeable. */
  async function ftsIds(kw, sinceISO){
    if(typeof _sb === 'undefined' || !_sb) return null;
    var q = toQuery(kw);
    if(q.length < 3) return null;
    var key = q + '||' + (sinceISO || '');
    var hit = _cache[key];
    if(hit && Date.now() - hit.at < TTL) return hit.ids;
    try {
      var ids = new Set();
      for(var from = 0; from < MAX_ROWS; from += PAGE){
        var req = _sb.from('decisions').select('id')
          .textSearch('fts', q, { config: 'french', type: 'websearch' })
          .order('id', { ascending: true })
          .range(from, from + PAGE - 1);
        if(sinceISO) req = req.gte('created_at', sinceISO);
        var res = await req;
        if(res.error) throw res.error;
        var rows = res.data || [];
        rows.forEach(function(r){ ids.add(String(r.id)); });
        if(rows.length < PAGE) break;
      }
      _cache[key] = { ids: ids, at: Date.now() };
      return ids;
    } catch(e){
      console.warn('[plein texte] index indisponible', e);
      return null;
    }
  }

  /* ── Recherche de l'écran « Recherche & entités » ── */
  var _search = { q: '', ids: null };
  var _timer = null;

  /* Ensemble d'identifiants valable pour la saisie en cours (sinon null). */
  window.ftsSearchIds = function(){
    var q = (typeof searchState !== 'undefined' && searchState.q || '').trim();
    return (q && _search.q === q) ? _search.ids : null;
  };

  /* À appeler à chaque saisie : interroge l'index après 350 ms sans frappe, puis redessine. */
  window.ftsSearchTrigger = function(){
    clearTimeout(_timer);
    var q = (typeof searchState !== 'undefined' && searchState.q || '').trim();
    if(q.length < 3){ _search = { q: '', ids: null }; return; }
    _timer = setTimeout(async function(){
      var ids = await ftsIds(q);
      var now = (searchState.q || '').trim();
      if(now !== q) return;                 /* la saisie a changé entre-temps */
      _search = { q: q, ids: ids };
      if(ids && typeof renderResults === 'function') renderResults();
    }, 350);
  };

  window.ftsIds = ftsIds;
})();
