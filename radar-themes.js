/* ===================== THÈMES PRÉDÉFINIS DU RADAR =====================
   Un thème n'est PAS un nouveau système de suivi : cocher « Urbanisme » crée une
   recherche ordinaire dans la liste du Radar (mêmes réglages de fréquence, mêmes
   notifications, mêmes pastilles dans « Publications récentes »), dont le mot-clé réunit
   plusieurs variantes séparées par « | » (combinées en OU, voir alertMatch et plein-texte.js).
   Décocher, ou supprimer la recherche depuis la liste, la retire : une seule liste à gérer.
   Les thèmes vivent dans le localStorage de ce navigateur comme le reste du Radar —
   rien n'est envoyé au serveur, donc rien ne révèle ce que chaque journaliste surveille.

   Dépend des globaux du module principal : ALERTS, saveAlerts, renderAlerts,
   renderDashboard, renderTimeline, radarMatchingIds, currentLang, $, escHtml. */
(function(){
  'use strict';

  var THEMES = [
    { id:'urbanisme',     fr:'Urbanisme',               de:'Städtebau',
      kw:'permis de construire|plan d\'aménagement|autorisation de bâtir|aménagement du territoire' },
    { id:'environnement', fr:'Environnement',           de:'Umwelt',
      kw:'protection de la nature|établissement classé|pollution|déchets|Natura 2000' },
    { id:'fiscalite',     fr:'Fiscalité',               de:'Steuerrecht',
      kw:'impôt|fiscal|TVA|administration des contributions' },
    { id:'travail',       fr:'Droit du travail',        de:'Arbeitsrecht',
      kw:'licenciement|contrat de travail|délégation du personnel|harcèlement moral' },
    { id:'etrangers',     fr:'Étrangers et asile',      de:'Ausländer und Asyl',
      kw:'protection internationale|titre de séjour|rétention|éloignement' },
    { id:'marches',       fr:'Marchés publics',         de:'Öffentliche Aufträge',
      kw:'marché public|soumission|adjudication|appel d\'offres' },
    { id:'fonction',      fr:'Fonction publique',       de:'Öffentlicher Dienst',
      kw:'fonctionnaire|agent de l\'État|conseil communal|stage' },
    { id:'presse',        fr:'Presse et libertés',      de:'Presse und Freiheiten',
      kw:'diffamation|liberté d\'expression|droit à l\'image|secret des sources' },
    { id:'finance',       fr:'Finance et sanctions',    de:'Finanzen und Sanktionen',
      kw:'gel de fonds|sanctions|CSSF|blanchiment' }
  ];

  function de(){ return typeof currentLang !== 'undefined' && currentLang === 'de'; }
  function find(id){ return THEMES.filter(function(t){ return t.id === id; })[0] || null; }
  function label(t){ return de() ? t.de : t.fr; }
  function active(id){ return ALERTS.some(function(a){ return a.theme === id; }); }

  /* Libellé affiché dans la liste du Radar à la place des variantes brutes. */
  window.radarThemeLabel = function(id){
    var t = find(id);
    return t ? label(t) : null;
  };

  function refreshAll(){
    saveAlerts();
    renderAlerts();
    if(typeof renderDashboard === 'function') renderDashboard();
    if(typeof renderTimeline === 'function') renderTimeline();
    if(typeof renderPublications === 'function') renderPublications();
  }

  function toggle(id){
    var t = find(id);
    if(!t) return;
    var idx = -1;
    ALERTS.forEach(function(a, i){ if(a.theme === id) idx = i; });
    if(idx >= 0){
      ALERTS.splice(idx, 1);
    } else {
      /* Même base silencieuse que pour une recherche créée à la main : l'existant ne compte
         pas comme nouveau. ftsSince borne la recherche plein texte aux arrivées futures. */
      ALERTS.unshift({ kw: t.kw, theme: t.id, freq: 'quotidien', on: true, matches: 0,
                       seen: radarMatchingIds(t.kw), ack: Date.now(), ftsSince: new Date().toISOString() });
    }
    refreshAll();
  }

  window.renderRadarThemes = function(){
    var root = $('#radar-themes');
    if(!root) return;
    var html = '<div class="section-h"><h2>' + escHtml(de() ? 'Themen' : 'Thèmes à suivre') + '</h2></div>' +
      '<p style="font-size:12.5px;color:var(--text-muted);margin:0 0 10px;">' +
      escHtml(de()
        ? 'Ein Klick legt eine thematische Suche in Ihrem Radar an, mit denselben Benachrichtigungen.'
        : 'Un clic crée une recherche thématique dans votre Radar, avec les mêmes notifications.') + '</p>' +
      '<div class="radar-themes" role="group">';
    THEMES.forEach(function(t){
      var on = active(t.id);
      html += '<button class="radar-theme" data-theme="' + escHtml(t.id) + '" aria-pressed="' + on + '">' +
        escHtml(label(t)) + '</button>';
    });
    root.innerHTML = html + '</div>';
  };

  var style = document.createElement('style');
  style.textContent =
    '.radar-themes{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:22px;}' +
    '.radar-theme{background:var(--card-bg,#fff);border:1px solid var(--card-border);border-radius:999px;padding:6px 14px;font:inherit;font-size:13px;cursor:pointer;color:inherit;}' +
    '.radar-theme:hover{border-color:var(--accent-blue);}' +
    '.radar-theme[aria-pressed="true"]{background:var(--accent-blue);border-color:var(--accent-blue);color:#fff;}';
  document.head.appendChild(style);

  document.addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('.radar-theme[data-theme]') : null;
    if(b) toggle(b.getAttribute('data-theme'));
  });
})();
