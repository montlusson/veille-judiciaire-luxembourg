/* ===================== PUBLICATIONS RÉCENTES =====================
   Rubrique « ce qui vient d'être publié » : décisions arrivées dans la base ces 7 ou 30
   derniers jours, regroupées par juridiction, sans mot-clé à saisir.

   Date retenue : `created_at` (date d'arrivée de la décision dans Supabase, donc de sa
   détection par l'extraction), PAS la date du jugement — une décision de septembre
   publiée en novembre est une nouveauté de novembre.

   Dépend des globaux du module principal : DECISIONS, currentLang, $, $all, escHtml,
   showScreen, openReader, refreshDecisions. Chargé après le script principal.

   « Déjà vu » : mémorisé dans le localStorage de ce navigateur (clé vj_pubs_seen), comme
   le Radar — rien n'est envoyé au serveur. La première visite part d'une base silencieuse :
   le stock existant ne compte pas comme nouveau. */
(function(){
  'use strict';

  var SEEN_KEY = 'vj_pubs_seen';
  var WINDOW_KEY = 'vj_pubs_window';
  var PER_GROUP = 8;
  var DAY = 24 * 3600 * 1000;

  var _days = 30;
  try { _days = localStorage.getItem(WINDOW_KEY) === '7' ? 7 : 30; } catch(e){}
  var _expanded = {};
  var FILTER_KEY = 'vj_pubs_filter';
  var _filter = 'all';
  try { var f0 = localStorage.getItem(FILTER_KEY); if(f0 === 'radar' || f0 === 'watch') _filter = f0; } catch(e){}

  /* ── Correspondances : une publication est « connectée » si elle touche ce que
     l'utilisateur suit déjà. Trois sources, aucune nouvelle liste à gérer :
     - Radar : ses mots-clés/thèmes actifs (localStorage), texte local + index plein texte ;
     - Affaire suivie : les numéros de rôle de la liste partagée (_watchlist) ;
     - Déjà vu dans vos dossiers : sociétés/avocats déjà présents dans ses annotations
       ou dans les affaires qu'il suit. ── */
  var _ftsRecent = {};       /* kw → Set d'ids arrivés ces 30 derniers jours (index plein texte) */
  var _ftsBusy = false;

  function activeAlerts(){
    return (typeof ALERTS !== 'undefined' && Array.isArray(ALERTS)) ? ALERTS.filter(function(a){ return a.on; }) : [];
  }
  function alertName(a){
    return (a.theme && typeof radarThemeLabel === 'function' && radarThemeLabel(a.theme)) || a.kw;
  }
  function radarHits(d){
    return activeAlerts().filter(function(a){
      var set = _ftsRecent[a.kw];
      return alertMatch(a.kw, decSearchText(d)) || (set && set.has(String(d.id)));
    });
  }

  function refreshFts(){
    if(_ftsBusy || typeof ftsIds !== 'function') return;
    var alerts = activeAlerts();
    if(!alerts.length) return;
    _ftsBusy = true;
    var since = new Date(Date.now() - 30 * DAY).toISOString();
    Promise.all(alerts.map(function(a){
      return ftsIds(a.kw, since).then(function(ids){ return [a.kw, ids]; });
    })).then(function(rs){
      var changed = false;
      rs.forEach(function(r){
        if(!r[1]) return;
        if(!_ftsRecent[r[0]] || _ftsRecent[r[0]].size !== r[1].size) changed = true;
        _ftsRecent[r[0]] = r[1];
      });
      _ftsBusy = false;
      if(changed) render();
    }).catch(function(){ _ftsBusy = false; });
  }

  function watchNums(){
    return (typeof _watchlist !== 'undefined' && Array.isArray(_watchlist)) ? _watchlist : [];
  }
  /* Numéro de rôle cherché dans la référence et l'extrait : « 54533C » exact, ou « 55868 »
     avec une lettre de suffixe éventuelle (« 55868R »). Au moins 4 chiffres, pour éviter les
     faux positifs. */
  function roleRegex(n){
    var m = /^(\d+)([A-Z]*)$/.exec(String(n).trim().toUpperCase());
    if(!m || m[1].length < 4) return null;
    return new RegExp('(^|[^A-Z0-9])' + m[1] + (m[2] || '[A-Z]?') + '($|[^A-Z0-9])');
  }
  function roleText(d){ return [d.ref, d.excerpt, d.fulltext].join(' ').toUpperCase(); }
  function watchHits(d){
    var text = roleText(d);
    return watchNums().filter(function(n){ var re = roleRegex(n); return re && re.test(text); });
  }

  function knownNames(){
    var names = {};
    var add = function(v){ v = String(v || '').trim().toLowerCase(); if(v.length >= 4) names[v] = true; };
    if(typeof ANNOTATIONS !== 'undefined'){
      Object.keys(ANNOTATIONS).forEach(function(id){ (ANNOTATIONS[id].parties || []).forEach(add); });
    }
    var data = (typeof AFFAIRES_DATA !== 'undefined' && AFFAIRES_DATA.length) ? AFFAIRES_DATA : [];
    var watched = {}; watchNums().forEach(function(n){ watched[n] = true; });
    data.forEach(function(a){ if(watched[a.num]){ add(a.demandeur); add(a.defendeur); add(a.avocat); } });
    return Object.keys(names);
  }
  function entityHit(d, known){
    var ents = ((d.entities && d.entities.societes) || []).concat((d.entities && d.entities.lawyers) || []);
    for(var i = 0; i < ents.length; i++){
      var e = String(ents[i]).trim().toLowerCase();
      if(e.length < 4) continue;
      for(var j = 0; j < known.length; j++){
        if(e.indexOf(known[j]) !== -1 || known[j].indexOf(e) !== -1) return ents[i];
      }
    }
    return null;
  }

  function de(){ return typeof currentLang !== 'undefined' && currentLang === 'de'; }
  function tx(fr, deu){ return de() ? deu : fr; }

  function ts(d){ var v = Date.parse(d && d.created_at); return isNaN(v) ? null : v; }

  /* Décisions réelles (hors démonstration) ayant une date d'arrivée exploitable. */
  function dated(){
    if(typeof DECISIONS === 'undefined' || !Array.isArray(DECISIONS)) return [];
    return DECISIONS.filter(function(d){ return d && !d._demo && ts(d) !== null; });
  }

  function readSeen(){
    try { var v = Date.parse(localStorage.getItem(SEEN_KEY)); return isNaN(v) ? null : v; }
    catch(e){ return null; }
  }
  function writeSeen(ms){
    try { localStorage.setItem(SEEN_KEY, new Date(ms).toISOString()); } catch(e){}
  }

  function latestArrival(list){
    return list.reduce(function(m, d){ return Math.max(m, ts(d)); }, 0);
  }

  /* Nombre de décisions arrivées depuis la dernière visite de la rubrique. */
  function unseenCount(list){
    var seen = readSeen();
    if(seen === null){
      if(list.length) writeSeen(latestArrival(list));   /* base silencieuse */
      return 0;
    }
    return list.filter(function(d){ return ts(d) > seen; }).length;
  }

  function updateBadge(list){
    var n = unseenCount(list);
    ['#pubs-badge', '#pubs-tile-badge'].forEach(function(sel){
      var badge = $(sel);
      if(!badge) return;
      badge.textContent = n > 99 ? '99+' : String(n);
      badge.hidden = n === 0;
    });
  }

  function injectStyles(){
    if(document.getElementById('pubs-styles')) return;
    var s = document.createElement('style');
    s.id = 'pubs-styles';
    s.textContent =
      '.pubs-bar{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap;margin:18px 0 20px;}' +
      '.pubs-sum{font-size:14px;color:var(--text-muted,#6B7399);}' +
      '.pubs-sum strong{color:var(--text,#1a1a2e);font-variant-numeric:tabular-nums;}' +
      '.pubs-win{display:inline-flex;border:1px solid var(--card-border);border-radius:var(--radius-md,8px);overflow:hidden;}' +
      '.pubs-win button{background:var(--card-bg,#fff);border:0;padding:6px 14px;font:inherit;font-size:13px;cursor:pointer;color:inherit;}' +
      '.pubs-win button[aria-pressed="true"]{background:var(--accent-blue);color:#fff;}' +
      '.pubs-group{background:var(--card-bg,#fff);border:1px solid var(--card-border);border-radius:var(--radius-lg,12px);margin-bottom:14px;overflow:hidden;}' +
      '.pubs-group h2{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0;padding:12px 16px;font-size:14px;font-weight:600;border-bottom:1px solid var(--row-sep);}' +
      '.pubs-count{font-variant-numeric:tabular-nums;font-weight:700;color:var(--accent-blue);}' +
      '.pubs-item{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px;width:100%;text-align:left;background:none;border:0;border-bottom:1px solid var(--row-sep);padding:9px 16px;font:inherit;font-size:13px;cursor:pointer;color:inherit;}' +
      '.pubs-item:hover,.pubs-item:focus-visible{background:var(--row-sep);}' +
      '.pubs-item:last-of-type{border-bottom:0;}' +
      '.pubs-ref{font-weight:600;overflow-wrap:anywhere;min-width:0;}' +
      '.pubs-meta{color:var(--text-muted,#6B7399);font-size:12px;margin-left:auto;white-space:nowrap;font-variant-numeric:tabular-nums;}' +
      '.pubs-new{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--accent-red);flex-shrink:0;align-self:center;}' +
      '.pubs-more{display:block;width:100%;padding:9px 16px;background:none;border:0;font:inherit;font-size:13px;color:var(--accent-blue);cursor:pointer;text-align:left;}' +
      '.pubs-empty{padding:32px 20px;text-align:center;color:var(--text-muted,#6B7399);background:var(--card-bg,#fff);border:1px solid var(--card-border);border-radius:var(--radius-lg,12px);}' +
      '.pubs-empty button{margin-top:12px;}' +
      '.pubs-filters{display:flex;gap:8px;flex-wrap:wrap;margin:-8px 0 18px;}' +
      '.pubs-filters button{background:var(--card-bg,#fff);border:1px solid var(--card-border);border-radius:999px;padding:5px 13px;font:inherit;font-size:13px;cursor:pointer;color:inherit;}' +
      '.pubs-filters button[aria-pressed="true"]{background:var(--accent-blue);border-color:var(--accent-blue);color:#fff;}' +
      '.pubs-tag{display:inline-block;border-radius:999px;padding:1px 8px;font-size:11px;font-weight:600;white-space:nowrap;}' +
      '.pubs-tag-radar{background:#FBF1DC;color:#8A6418;}' +
      '.pubs-tag-watch{background:#E3EEF9;color:#1F4E86;}' +
      '.pubs-tag-known{background:#EAF3EA;color:#2D6A3A;}' +
      '.pubs-hint{font-size:12.5px;color:var(--text-muted,#6B7399);margin:-8px 0 16px;}' +
      '.pubs-hint button{background:none;border:0;padding:0;font:inherit;color:var(--accent-blue);cursor:pointer;text-decoration:underline;}';
    document.head.appendChild(s);
  }

  function tagHtml(t){
    var h = '';
    if(t.radar.length){
      var first = alertName(t.radar[0]);
      h += '<span class="pubs-tag pubs-tag-radar">Radar : ' + escHtml(first) + (t.radar.length > 1 ? ' +' + (t.radar.length - 1) : '') + '</span>';
    }
    if(t.watch.length){
      h += '<span class="pubs-tag pubs-tag-watch" title="N° ' + escHtml(t.watch.join(', ')) + '">' + escHtml(tx('Affaire suivie', 'Verfolgtes Verfahren')) + '</span>';
    }
    if(t.known){
      h += '<span class="pubs-tag pubs-tag-known" title="' + escHtml(t.known) + '">' + escHtml(tx('Déjà vu dans vos dossiers', 'Bereits in Ihren Akten')) + '</span>';
    }
    return h;
  }

  function fmtDay(ms){
    return new Date(ms).toLocaleDateString(de() ? 'de-LU' : 'fr-LU', { day:'2-digit', month:'2-digit' });
  }

  function emptyState(msg, withRefresh){
    return '<div class="pubs-empty"><div>' + escHtml(msg) + '</div>' +
      (withRefresh ? '<button class="btn btn-primary" data-pubs-refresh>' +
        escHtml(tx('Mettre à jour l\'index', 'Index aktualisieren')) + '</button>' : '') + '</div>';
  }

  function render(){
    var root = $('#pubs-root');
    var all = dated();
    updateBadge(all);
    if(!root) return;
    injectStyles();

    var real = (typeof DECISIONS !== 'undefined' && Array.isArray(DECISIONS))
      ? DECISIONS.filter(function(d){ return d && !d._demo; }) : [];
    if(!real.length){
      root.innerHTML = emptyState(tx('Les décisions ne sont pas encore chargées.', 'Die Entscheidungen sind noch nicht geladen.'), true);
      return;
    }
    if(!all.length){
      /* Index mis en cache avant l'ajout de la date d'arrivée, ou chargé hors Supabase. */
      root.innerHTML = emptyState(tx(
        'La date de publication n\'est pas disponible dans l\'index chargé. Mettez-le à jour pour activer cette rubrique.',
        'Das Veröffentlichungsdatum fehlt im geladenen Index. Aktualisieren Sie ihn, um diese Rubrik zu aktivieren.'), true);
      return;
    }

    var now = Date.now();
    var seen = readSeen();
    var recent = all.filter(function(d){ return ts(d) >= now - _days * DAY; });
    recent.sort(function(a, b){ return ts(b) - ts(a); });

    /* Étiquettes de connexion de chaque publication récente */
    var known = knownNames();
    var tagsOf = {};
    recent.forEach(function(d){
      tagsOf[d.id] = { radar: radarHits(d), watch: watchHits(d), known: entityHit(d, known) };
    });
    var nRadar = recent.filter(function(d){ return tagsOf[d.id].radar.length; }).length;
    var nWatch = recent.filter(function(d){ return tagsOf[d.id].watch.length; }).length;
    var visible = _filter === 'radar' ? recent.filter(function(d){ return tagsOf[d.id].radar.length; })
                : _filter === 'watch' ? recent.filter(function(d){ return tagsOf[d.id].watch.length; })
                : recent;

    var groups = {};
    visible.forEach(function(d){
      var k = d.jur || tx('Juridiction inconnue', 'Unbekanntes Gericht');
      (groups[k] = groups[k] || []).push(d);
    });
    var names = Object.keys(groups).sort(function(a, b){ return groups[b].length - groups[a].length; });

    var last = latestArrival(all);
    var html = '<div class="pubs-bar"><div class="pubs-sum"><strong>' + recent.length + '</strong> ' +
      escHtml(tx(recent.length > 1 ? 'décisions publiées' : 'décision publiée',
                 recent.length > 1 ? 'veröffentlichte Entscheidungen' : 'veröffentlichte Entscheidung')) +
      ' ' + escHtml(tx('sur les ' + _days + ' derniers jours', 'in den letzten ' + _days + ' Tagen')) +
      ' · ' + escHtml(tx('dernière arrivée le ', 'zuletzt am ')) + escHtml(fmtDay(last)) + '</div>' +
      '<div class="pubs-win" role="group" aria-label="' + escHtml(tx('Période', 'Zeitraum')) + '">' +
      '<button data-pubs-win="7" aria-pressed="' + (_days === 7) + '">' + escHtml(tx('7 jours', '7 Tage')) + '</button>' +
      '<button data-pubs-win="30" aria-pressed="' + (_days === 30) + '">' + escHtml(tx('30 jours', '30 Tage')) + '</button>' +
      '</div></div>';

    html += '<div class="pubs-filters" role="group" aria-label="' + escHtml(tx('Filtrer', 'Filtern')) + '">' +
      '<button data-pubs-filter="all" aria-pressed="' + (_filter === 'all') + '">' + escHtml(tx('Toutes', 'Alle')) + ' (' + recent.length + ')</button>' +
      '<button data-pubs-filter="radar" aria-pressed="' + (_filter === 'radar') + '">' + escHtml(tx('Mes mots-clés', 'Meine Stichwörter')) + ' (' + nRadar + ')</button>' +
      '<button data-pubs-filter="watch" aria-pressed="' + (_filter === 'watch') + '">' + escHtml(tx('Affaires suivies', 'Verfolgte Verfahren')) + ' (' + nWatch + ')</button></div>';

    if(_filter === 'radar' && !activeAlerts().length){
      html += '<p class="pubs-hint">' + escHtml(tx('Aucun mot-clé actif. ', 'Kein aktives Stichwort. ')) +
        '<button data-pubs-goto="veille">' + escHtml(tx('Choisir des thèmes ou des mots-clés dans le Radar', 'Themen oder Stichwörter im Radar wählen')) + '</button></p>';
    } else if(_filter === 'watch' && !watchNums().length){
      html += '<p class="pubs-hint">' + escHtml(tx('Aucune affaire suivie. ', 'Keine verfolgten Verfahren. ')) +
        '<button data-pubs-goto="affaires">' + escHtml(tx('Suivre une affaire', 'Ein Verfahren verfolgen')) + '</button></p>';
    }

    if(!visible.length){
      html += emptyState(_filter === 'all'
        ? tx('Aucune décision publiée sur cette période.', 'Keine Entscheidung in diesem Zeitraum veröffentlicht.')
        : tx('Aucune publication ne correspond à ce filtre sur la période.', 'Keine Veröffentlichung entspricht diesem Filter im Zeitraum.'), false);
    }

    names.forEach(function(name){
      var items = groups[name];
      var open = !!_expanded[name];
      var shown = open ? items : items.slice(0, PER_GROUP);
      html += '<section class="pubs-group"><h2><span>' + escHtml(name) + '</span><span class="pubs-count">' + items.length + '</span></h2>';
      shown.forEach(function(d){
        var isNew = seen !== null && ts(d) > seen;
        html += '<button class="pubs-item" data-pubs-id="' + escHtml(d.id) + '">' +
          (isNew ? '<span class="pubs-new" title="' + escHtml(tx('Nouveau depuis votre dernière visite', 'Neu seit Ihrem letzten Besuch')) + '"></span>' : '') +
          '<span class="pubs-ref">' + escHtml(d.ref || d.id) + '</span>' +
          '<span>' + escHtml(d.type || '') + '</span>' + tagHtml(tagsOf[d.id]) +
          '<span class="pubs-meta">' + escHtml(tx('arrivée le ', 'eingegangen ')) + escHtml(fmtDay(ts(d))) +
          (d.date ? ' · ' + escHtml(d.date) : '') + '</span></button>';
      });
      if(items.length > PER_GROUP){
        html += '<button class="pubs-more" data-pubs-more="' + escHtml(name) + '">' +
          escHtml(open ? tx('Réduire', 'Weniger anzeigen')
                       : tx('Voir les ' + items.length + ' décisions', 'Alle ' + items.length + ' Entscheidungen anzeigen')) + '</button>';
      }
      html += '</section>';
    });

    root.innerHTML = html;
    refreshFts();
  }

  /* Ouvrir la rubrique = tout marquer comme vu (la pastille s'éteint, les points restent
     affichés pour cette visite grâce à l'ancien repère conservé jusqu'au prochain rendu). */
  function markSeen(){
    var all = dated();
    if(all.length) writeSeen(latestArrival(all));
    ['#pubs-badge', '#pubs-tile-badge'].forEach(function(sel){
      var badge = $(sel);
      if(badge) badge.hidden = true;
    });
  }

  document.addEventListener('click', function(e){
    var el = e.target.closest ? e.target.closest('[data-pubs-id],[data-pubs-win],[data-pubs-more],[data-pubs-refresh],[data-pubs-filter],[data-pubs-goto],.navbtn[data-target="publications"],.action-tile[data-target="publications"]') : null;
    if(!el) return;
    if(el.hasAttribute('data-pubs-id')){
      openDecisionFocus(el.getAttribute('data-pubs-id'), 'publications');
    } else if(el.hasAttribute('data-pubs-win')){
      _days = el.getAttribute('data-pubs-win') === '7' ? 7 : 30;
      try { localStorage.setItem(WINDOW_KEY, String(_days)); } catch(err){}
      render();
    } else if(el.hasAttribute('data-pubs-more')){
      var n = el.getAttribute('data-pubs-more');
      _expanded[n] = !_expanded[n];
      render();
    } else if(el.hasAttribute('data-pubs-filter')){
      _filter = el.getAttribute('data-pubs-filter');
      try { localStorage.setItem(FILTER_KEY, _filter); } catch(err){}
      render();
    } else if(el.hasAttribute('data-pubs-goto')){
      showScreen(el.getAttribute('data-pubs-goto'));
    } else if(el.hasAttribute('data-pubs-refresh')){
      if(typeof refreshDecisions === 'function') refreshDecisions(true);
    } else {
      /* navigation vers la rubrique : rendu avec les points « nouveau », puis marquage vu */
      render();
      markSeen();
    }
  });

  /* Nombre de décisions arrivées depuis `days` jours, ou null si l'index chargé n'a pas la
     date d'arrivée (cache ancien, chargement hors Supabase). Utilisé par le KPI du tableau de bord. */
  window.publicationsCount = function(days){
    var all = dated();
    if(!all.length) return null;
    var cut = Date.now() - days * DAY;
    return all.filter(function(d){ return ts(d) >= cut; }).length;
  };

  /* Décisions de la base portant ce numéro de rôle (écran Affaires en cours). */
  window.decisionsForRole = function(num){
    var re = roleRegex(num);
    if(!re || typeof DECISIONS === 'undefined') return [];
    return DECISIONS.filter(function(d){ return d && !d._demo && re.test(roleText(d)); });
  };

  /* Ouvre « Recherche & entités » avec cette saisie déjà lancée. */
  window.openSearchFor = function(q){
    var input = $('#search-input');
    if(input) input.value = q;
    searchState.q = q;
    showScreen('recherche');
    if(typeof ftsSearchTrigger === 'function') ftsSearchTrigger();
    renderResults();
  };

  window.renderPublications = render;
})();
