/* ===================== LECTURE ISOLÉE D'UNE DÉCISION =====================
   Quand l'utilisateur clique sur UNE décision depuis un autre écran (Publications récentes,
   Radar, lien partagé), il veut lire cette décision — pas se retrouver dans l'écran
   « Recherche & entités » avec le moteur, les filtres et la liste de toutes les décisions.

   Ce fichier ouvre donc la décision dans l'écran de lecture SEUL (liste et filtres masqués)
   avec un lien de retour vers l'écran d'origine. L'écran « Recherche & entités » complet
   reste ce qu'on obtient en l'ouvrant volontairement (menu, tuile, recherche lancée) :
   showScreen() retire alors ce mode (voir veille-judiciaire-luxembourg.html).

   Dépend des globaux du module principal : showScreen, openReader, currentLang, $. */
(function(){
  'use strict';

  var ORIGINS = {
    publications: { target: 'publications', fr: 'Publications récentes', de: 'Neue Veröffentlichungen' },
    veille:       { target: 'veille',        fr: 'Radar décisions',       de: 'Entscheidungsradar' },
    affaires:     { target: 'affaires',      fr: 'Affaires en cours',     de: 'Laufende Verfahren' },
    liste:        { target: 'recherche',     fr: 'Toutes les décisions',  de: 'Alle Entscheidungen' }
  };
  var _origin = ORIGINS.liste;

  function de(){ return typeof currentLang !== 'undefined' && currentLang === 'de'; }

  function section(){ return document.querySelector('.screen[data-screen="recherche"]'); }

  /* Ouvre la décision `id` seule ; `from` = clé de ORIGINS (écran d'origine du clic). */
  window.openDecisionFocus = function(id, from){
    _origin = ORIGINS[from] || ORIGINS.liste;
    showScreen('recherche');                 /* retire un éventuel mode précédent */
    var sec = section();
    if(sec) sec.classList.add('focus-mode');
    var back = document.querySelector('[data-focus-back]');
    if(back){
      back.textContent = '← ' + (de() ? _origin.de : _origin.fr);
    }
    /* Le menu garde l'écran d'origine en surbrillance : on n'a pas « ouvert la recherche ». */
    if(_origin.target !== 'recherche'){
      document.querySelectorAll('.navbtn').forEach(function(b){
        if(b.dataset.target === _origin.target) b.setAttribute('aria-current', 'page');
        else b.removeAttribute('aria-current');
      });
    }
    openReader(id);
    window.scrollTo(0, 0);
  };

  var style = document.createElement('style');
  style.textContent =
    '.focus-back{display:none;}' +   /* aspect partagé avec .back-dash : voir la feuille de style principale */
    '.screen[data-screen="recherche"].focus-mode .focus-back{display:inline-flex;}' +
    '.screen[data-screen="recherche"].focus-mode .back-dash,' +
    '.screen[data-screen="recherche"].focus-mode .eyebrow,' +
    '.screen[data-screen="recherche"].focus-mode .title,' +
    '.screen[data-screen="recherche"].focus-mode .intro,' +
    '.screen[data-screen="recherche"].focus-mode .section-notice,' +
    '.screen[data-screen="recherche"].focus-mode .controlbar,' +
    '.screen[data-screen="recherche"].focus-mode #results-count,' +
    '.screen[data-screen="recherche"].focus-mode .recherche-left{display:none;}' +
    '.screen[data-screen="recherche"].focus-mode .recherche-split{display:block;height:auto;min-height:0;}' +
    '.screen[data-screen="recherche"].focus-mode .recherche-right{border:1px solid var(--card-border);border-radius:var(--radius-lg);overflow:visible;}' +
    '.screen[data-screen="recherche"].focus-mode .detail-text-zone{overflow:visible;}';
  document.head.appendChild(style);

  document.addEventListener('click', function(e){
    var b = e.target.closest ? e.target.closest('[data-focus-back]') : null;
    if(b) showScreen(_origin.target);
  });
})();
