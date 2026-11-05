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
    var badge = $('#pubs-badge');
    if(!badge) return;
    var n = unseenCount(list);
    badge.textContent = n > 99 ? '99+' : String(n);
    badge.hidden = n === 0;
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
      '.pubs-item{display:flex;align-items:baseline;gap:10px;width:100%;text-align:left;background:none;border:0;border-bottom:1px solid var(--row-sep);padding:9px 16px;font:inherit;font-size:13px;cursor:pointer;color:inherit;}' +
      '.pubs-item:hover,.pubs-item:focus-visible{background:var(--row-sep);}' +
      '.pubs-item:last-of-type{border-bottom:0;}' +
      '.pubs-ref{font-weight:600;white-space:nowrap;}' +
      '.pubs-meta{color:var(--text-muted,#6B7399);font-size:12px;margin-left:auto;white-space:nowrap;font-variant-numeric:tabular-nums;}' +
      '.pubs-new{display:inline-block;width:8px;height:8px;border-radius:50%;background:var(--accent-red);flex-shrink:0;align-self:center;}' +
      '.pubs-more{display:block;width:100%;padding:9px 16px;background:none;border:0;font:inherit;font-size:13px;color:var(--accent-blue);cursor:pointer;text-align:left;}' +
      '.pubs-empty{padding:32px 20px;text-align:center;color:var(--text-muted,#6B7399);background:var(--card-bg,#fff);border:1px solid var(--card-border);border-radius:var(--radius-lg,12px);}' +
      '.pubs-empty button{margin-top:12px;}';
    document.head.appendChild(s);
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

    var groups = {};
    recent.forEach(function(d){
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

    if(!recent.length){
      html += emptyState(tx('Aucune décision publiée sur cette période.', 'Keine Entscheidung in diesem Zeitraum veröffentlicht.'), false);
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
          '<span>' + escHtml(d.type || '') + '</span>' +
          '<span class="pubs-meta">' + escHtml(tx('arrivée le ', 'eingegangen ')) + escHtml(fmtDay(ts(d))) +
          ' · ' + escHtml(d.date || '') + '</span></button>';
      });
      if(items.length > PER_GROUP){
        html += '<button class="pubs-more" data-pubs-more="' + escHtml(name) + '">' +
          escHtml(open ? tx('Réduire', 'Weniger anzeigen')
                       : tx('Voir les ' + items.length + ' décisions', 'Alle ' + items.length + ' Entscheidungen anzeigen')) + '</button>';
      }
      html += '</section>';
    });

    root.innerHTML = html;
  }

  /* Ouvrir la rubrique = tout marquer comme vu (la pastille s'éteint, les points restent
     affichés pour cette visite grâce à l'ancien repère conservé jusqu'au prochain rendu). */
  function markSeen(){
    var all = dated();
    if(all.length) writeSeen(latestArrival(all));
    var badge = $('#pubs-badge');
    if(badge) badge.hidden = true;
  }

  document.addEventListener('click', function(e){
    var el = e.target.closest ? e.target.closest('[data-pubs-id],[data-pubs-win],[data-pubs-more],[data-pubs-refresh],.navbtn[data-target="publications"],.action-tile[data-target="publications"]') : null;
    if(!el) return;
    if(el.hasAttribute('data-pubs-id')){
      showScreen('recherche');
      openReader(el.getAttribute('data-pubs-id'));
    } else if(el.hasAttribute('data-pubs-win')){
      _days = el.getAttribute('data-pubs-win') === '7' ? 7 : 30;
      try { localStorage.setItem(WINDOW_KEY, String(_days)); } catch(err){}
      render();
    } else if(el.hasAttribute('data-pubs-more')){
      var n = el.getAttribute('data-pubs-more');
      _expanded[n] = !_expanded[n];
      render();
    } else if(el.hasAttribute('data-pubs-refresh')){
      if(typeof refreshDecisions === 'function') refreshDecisions(true);
    } else {
      /* navigation vers la rubrique : rendu avec les points « nouveau », puis marquage vu */
      render();
      markSeen();
    }
  });

  window.renderPublications = render;
})();
