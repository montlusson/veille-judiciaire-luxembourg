/* ===================== DÉCISIONS ADMINISTRATIVES (collage assisté) =====================
   Les juridictions administratives ne sont pas dans les données ouvertes de data.public.lu
   et ja.public.lu interdit les robots : ces décisions entrent donc par COLLAGE (liste copiée
   de justice.public.lu ou adresses de PDF), jamais par extraction automatique.

   Ce fichier :
   1. charge la table `decisions_admin` (Supabase, lecture réservée @reporter.lu) ;
   2. en fait des objets « décision » ordinaires ajoutés à DECISIONS : la recherche, le Radar,
      « Publications récentes » (pastille « Affaire suivie » par numéro de rôle) et le lecteur
      fonctionnent sans cas particulier ;
   3. affiche la zone de collage dans « Publications récentes », avec un aperçu AVANT toute
      écriture (nouvelles / à compléter / déjà en base / illisibles).

   Dépend des globaux du module principal : DECISIONS, _sb, _currentUser, currentLang, $,
   escHtml, renderAll, et de AdminParse (admin-parse.js). Toutes les valeurs affichées sont
   échappées ; la base applique en plus des contraintes CHECK (decisions-admin-schema.sql). */
(function(){
  'use strict';

  var PAGE = 1000;
  var MAX_ENTRIES = 200;                 /* par collage */
  var COLS = 'role_num,ecli,juridiction,instance,chambre,contentieux,date_audience,resume,url,created_at';
  var RE_PDF = /^https:\/\/ja\.public\.lu\/[A-Za-z0-9_.\/-]{1,150}\.pdf$/;

  var _rows = [];
  var _loaded = false, _loading = false;
  var _pending = null;                   /* résultat d'analyse en attente de validation */

  function de(){ return typeof currentLang !== 'undefined' && currentLang === 'de'; }
  function tx(fr, deu){ return de() ? deu : fr; }
  function digits(role){ return String(role).replace(/[A-Z]+$/, ''); }
  function rich(r){ return !!(r.ecli || r.resume || r.date_audience); }

  /* ── Chargement ── */
  async function load(){
    if(_loading || typeof _sb === 'undefined' || !_sb || typeof _currentUser === 'undefined' || !_currentUser) return;
    _loading = true;
    try {
      var all = [];
      for(var from = 0; ; from += PAGE){
        var res = await _sb.from('decisions_admin').select(COLS)
          .order('role_num', { ascending: true }).range(from, from + PAGE - 1);
        if(res.error) throw res.error;
        all = all.concat(res.data || []);
        if(!res.data || res.data.length < PAGE) break;
      }
      _rows = all;
      _loaded = true;
      if(typeof renderAll === 'function') renderAll();
    } catch(e){
      console.warn('[décisions administratives] lecture impossible (table absente ?)', e);
      _loaded = true;      /* ne pas réessayer en boucle ; un rechargement de page retentera */
    } finally { _loading = false; }
  }

  /* ── Lignes → objets « décision » ordinaires ── */
  /* Affaire connue (convocations déposées) portant les mêmes chiffres : une décision enregistrée
     par son seul lien PDF n'a ni résumé ni parties, on emprunte alors ceux de l'affaire. */
  function knownAffaire(role){
    var list = (typeof AFFAIRES_DATA !== 'undefined' && Array.isArray(AFFAIRES_DATA)) ? AFFAIRES_DATA : [];
    var d = digits(role);
    return list.filter(function(a){ return a && a.num && digits(String(a.num).toUpperCase()) === d; })[0] || null;
  }
  function affaireText(a){
    if(!a) return '';
    var parties = [a.demandeur, a.defendeur].filter(Boolean).join(' c/ ');
    return [a.matiere, parties].filter(Boolean).join(' — ');
  }

  function toDecision(r){
    var aff = rich(r) ? null : knownAffaire(r.role_num);
    var affTxt = affaireText(aff);
    var url = (r.url && RE_PDF.test(r.url)) ? r.url : null;
    var pdf = url || AdminParse.probableUrl(r.role_num);
    var year = r.date_audience ? +String(r.date_audience).slice(0, 4) : 0;
    return {
      id: 'adm-' + r.role_num,
      ref: r.juridiction + ' — N° ' + r.role_num,
      date: r.date_audience || '',
      jur: r.juridiction,
      group: 'Juridictions administratives',
      type: r.instance === 'Référé' ? 'Référé' : r.instance ? 'Jugement' : 'Décision',
      excerpt: (r.resume || affTxt).slice(0, 200),
      fulltext: r.resume || ((affTxt ? affTxt + '. ' : '') +
        tx('Décision enregistrée à partir de son lien PDF. Ouvrez le PDF pour la lire.',
           'Entscheidung anhand ihres PDF-Links erfasst. Öffnen Sie das PDF, um sie zu lesen.')),
      entities: { societes: [], lawyers: [], montants: [], dates: [], articles: [] },
      source_year: year,
      created_at: r.created_at,
      _admin: true, _pdf: pdf, _pdfProbable: !url, _ecli: r.ecli || null
    };
  }

  /* Appelée au début de renderAll() : (re)place les décisions administratives dans DECISIONS. */
  window.adminMerge = function(){
    if(!_loaded && !_loading) load();
    if(typeof DECISIONS === 'undefined') return;
    /* Un lien collé sans suffixe (55868) puis une liste (55868R) donnent deux lignes pour une
       même décision : on masque la ligne pauvre quand une plus riche porte les mêmes chiffres. */
    var richDigits = {};
    _rows.forEach(function(r){ if(rich(r)) richDigits[digits(r.role_num)] = r.role_num; });
    var shown = _rows.filter(function(r){
      return rich(r) || !richDigits[digits(r.role_num)] || richDigits[digits(r.role_num)] === r.role_num;
    });
    var others = DECISIONS.filter(function(d){ return !d._admin; });
    var mine = shown.map(toDecision);
    if(!mine.length && others.length === DECISIONS.length) return;   /* rien à changer */
    DECISIONS = others.concat(mine);
  };

  /* Bloc HTML du lecteur : lien vers le PDF (ouvert par un clic de l'utilisateur) et ECLI. */
  window.adminPdfLinkHtml = function(d){
    if(!d || !d._admin) return '';
    var h = '<div class="detail-full-meta" style="margin-top:6px;">';
    if(d._ecli) h += escHtml(d._ecli) + ' · ';
    if(d._pdf && RE_PDF.test(d._pdf)){
      h += '<a href="' + escHtml(d._pdf) + '" target="_blank" rel="noopener noreferrer">' +
        escHtml(tx('Ouvrir le PDF sur ja.public.lu', 'PDF auf ja.public.lu öffnen')) + '</a>' +
        (d._pdfProbable ? ' <span style="opacity:.7">(' + escHtml(tx('adresse probable, non vérifiée', 'wahrscheinliche Adresse, nicht geprüft')) + ')</span>' : '');
    } else {
      h += escHtml(tx('PDF : adresse inconnue', 'PDF: Adresse unbekannt'));
    }
    return h + '</div>';
  };

  /* ── Zone de collage ── */
  /* Ligne existante correspondant à cette entrée : même numéro de rôle, sinon même numéro
     sans suffixe (le lien 55868.pdf désigne la décision 55868R déjà enregistrée). */
  function targetRow(e){
    return _rows.filter(function(r){ return r.role_num === e.role; })[0]
        || _rows.filter(function(r){ return digits(r.role_num) === digits(e.role) && rich(r); })[0] || null;
  }

  function statusOf(e){
    var cur = targetRow(e);
    if(!cur) return 'new';
    var adds = (e.ecli && !cur.ecli) || (e.resume && !cur.resume) || (e.date && !cur.date_audience)
            || (e.url && !cur.url) || (e.chambre && !cur.chambre) || (e.instance && !cur.instance);
    return adds ? 'complete' : 'same';
  }

  function labelOf(st){
    return st === 'new' ? tx('nouvelle', 'neu') : st === 'complete' ? tx('à compléter', 'zu ergänzen') : tx('déjà en base', 'bereits vorhanden');
  }

  function previewHtml(){
    if(!_pending) return '';
    var list = _pending.entries;
    var counts = { new: 0, complete: 0, same: 0 };
    var rows = list.map(function(e){
      var st = statusOf(e); counts[st]++;
      var bits = [e.juridiction, e.instance, e.chambre ? tx('ch. ', 'Kammer ') + e.chambre : null, e.date].filter(Boolean).join(' · ');
      return '<tr><td><strong>' + escHtml(e.role) + '</strong></td><td>' + escHtml(bits || '—') + '</td>' +
        '<td>' + escHtml(e.resume ? e.resume.slice(0, 110) + (e.resume.length > 110 ? '…' : '') : (e.url ? tx('lien PDF seul', 'nur PDF-Link') : '—')) + '</td>' +
        '<td class="admin-st admin-st-' + st + '">' + escHtml(labelOf(st)) + '</td></tr>';
    }).join('');
    var todo = counts.new + counts.complete;
    var head = list.length
      ? '<p class="admin-sum"><strong>' + list.length + '</strong> ' + escHtml(tx('reconnue(s)', 'erkannt')) + ' · ' +
        counts.new + ' ' + escHtml(tx('nouvelle(s)', 'neu')) + ' · ' + counts.complete + ' ' + escHtml(tx('à compléter', 'zu ergänzen')) + ' · ' +
        counts.same + ' ' + escHtml(tx('déjà en base', 'bereits vorhanden')) +
        (_pending.ignored ? ' · ' + _pending.ignored + ' ' + escHtml(tx('illisible(s)', 'unlesbar')) : '') + '</p>'
      : '<p class="admin-sum">' + escHtml(tx('Aucun lien reconnu. Un lien ressemble à https://ja.public.lu/45001-50000/49856.pdf',
                                           'Kein Link erkannt. Ein Link sieht so aus: https://ja.public.lu/45001-50000/49856.pdf')) + '</p>';
    var table = list.length
      ? '<table class="admin-table"><thead><tr><th>' + escHtml(tx('Rôle', 'Rolle')) + '</th><th>' + escHtml(tx('Détail', 'Detail')) + '</th><th>' +
        escHtml(tx('Résumé', 'Zusammenfassung')) + '</th><th></th></tr></thead><tbody>' + rows + '</tbody></table>' : '';
    var save = todo
      ? '<button class="btn btn-primary" data-admin-save>' + escHtml(tx('Enregistrer ', 'Speichern ')) + todo + '</button> ' : '';
    return head + table + '<div class="admin-actions">' + save +
      '<button class="btn btn-secondary" data-admin-clear>' + escHtml(tx('Effacer', 'Zurücksetzen')) + '</button></div>';
  }

  function ensureStyles(){
    if(document.getElementById('admin-styles')) return;
    var s = document.createElement('style'); s.id = 'admin-styles';
    s.textContent =
      '.pubs-admin{background:var(--card-bg,#fff);border:1px solid var(--card-border);border-radius:var(--radius-lg,12px);padding:10px 16px;margin:14px 0 4px;}' +
      '.pubs-admin summary{cursor:pointer;font-weight:600;font-size:14px;}' +
      '.pubs-admin p{font-size:12.5px;color:var(--text-muted,#6B7399);margin:10px 0;}' +
      '.pubs-admin textarea{width:100%;min-height:110px;box-sizing:border-box;font:12.5px/1.4 monospace;padding:10px;border:1px solid var(--card-border);border-radius:8px;resize:vertical;}' +
      '.admin-actions{display:flex;gap:8px;margin:10px 0 4px;flex-wrap:wrap;}' +
      '.admin-table{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px;}' +
      '.admin-table th,.admin-table td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--row-sep);vertical-align:top;}' +
      '.admin-st{white-space:nowrap;font-weight:600;}' +
      '.admin-st-new{color:#1A7F3C;}.admin-st-complete{color:#8A6418;}.admin-st-same{color:var(--text-muted,#6B7399);}' +
      '.admin-msg{font-size:13px;margin:8px 0;}';
    document.head.appendChild(s);
  }

  function renderPaste(force){
    var root = $('#pubs-admin-root');
    if(!root) return;
    var lang = de() ? 'de' : 'fr';
    if(!force && root.getAttribute('data-ready') === lang) return;
    ensureStyles();
    var prev = $('#admin-paste') ? $('#admin-paste').value : '';
    var open = root.querySelector('details') ? root.querySelector('details').open : false;
    root.innerHTML = '<details class="pubs-admin"' + (open ? ' open' : '') + '><summary>' +
      escHtml(tx('Ajouter des décisions administratives', 'Verwaltungsentscheidungen hinzufügen')) + '</summary>' +
      '<p>' + escHtml(tx(
        'Collez un ou plusieurs liens de PDF des juridictions administratives (ja.public.lu). L\'aperçu apparaît tout seul et rien n\'est enregistré avant votre validation.',
        'Fügen Sie einen oder mehrere PDF-Links der Verwaltungsgerichte ein (ja.public.lu). Die Vorschau erscheint automatisch, gespeichert wird erst nach Ihrer Bestätigung.')) + '</p>' +
      '<textarea id="admin-paste" maxlength="60000" placeholder="https://ja.public.lu/45001-50000/49856.pdf" aria-label="' + escHtml(tx('Liens de PDF', 'PDF-Links')) + '"></textarea>' +
      '<div id="admin-msg" class="admin-msg" role="status"></div><div id="admin-preview">' + previewHtml() + '</div></details>';
    $('#admin-paste').value = prev;
    root.setAttribute('data-ready', lang);
  }

  function say(msg){ var m = $('#admin-msg'); if(m) m.textContent = msg || ''; }
  function refreshPreview(){ var p = $('#admin-preview'); if(p) p.innerHTML = previewHtml(); }

  function analyze(){
    var text = ($('#admin-paste') || {}).value || '';
    var res = AdminParse.parse(text);
    if(res.entries.length > MAX_ENTRIES){ res.ignored += res.entries.length - MAX_ENTRIES; res.entries = res.entries.slice(0, MAX_ENTRIES); }
    _pending = res;
    say('');
    refreshPreview();
  }

  async function save(){
    if(!_pending || typeof _sb === 'undefined' || !_sb || !_currentUser){ say(tx('Connexion requise.', 'Anmeldung erforderlich.')); return; }
    var btn = document.querySelector('[data-admin-save]'); if(btn) btn.disabled = true;
    var ok = 0, failed = 0, firstErr = '';
    for(var i = 0; i < _pending.entries.length; i++){
      var e = _pending.entries[i];
      var st = statusOf(e);
      if(st === 'same') continue;
      var fields = { juridiction: e.juridiction };
      if(e.ecli) fields.ecli = e.ecli;
      if(e.instance) fields.instance = e.instance;
      if(e.chambre) fields.chambre = e.chambre;
      if(e.contentieux) fields.contentieux = e.contentieux;
      if(e.date) fields.date_audience = e.date;
      if(e.resume) fields.resume = e.resume;
      if(e.url) fields.url = e.url;
      try {
        var existing = targetRow(e);
        var res = existing
          ? await _sb.from('decisions_admin').update(fields).eq('role_num', existing.role_num)
          : await _sb.from('decisions_admin').insert(Object.assign({ role_num: e.role, added_by: _currentUser.email }, fields));
        if(res.error) throw res.error;
        ok++;
      } catch(err){
        failed++; if(!firstErr) firstErr = String(err && err.message || err).slice(0, 160);
      }
    }
    say(ok + ' ' + tx('enregistrée(s)', 'gespeichert') + (failed ? ' · ' + failed + ' ' + tx('en échec', 'fehlgeschlagen') + ' (' + firstErr + ')' : ''));
    if(ok){
      _pending = null; var ta = $('#admin-paste'); if(ta) ta.value = '';
      refreshPreview();
      _loaded = false; load();           /* recharge puis renderAll() */
    } else if(btn) btn.disabled = false;
  }

  var _autoTimer = null;
  document.addEventListener('input', function(e){
    if(!e.target || e.target.id !== 'admin-paste') return;
    clearTimeout(_autoTimer);
    _autoTimer = setTimeout(function(){
      if(!(e.target.value || '').trim()){ _pending = null; say(''); refreshPreview(); return; }
      analyze();
    }, 250);
  });

  document.addEventListener('click', function(e){
    var el = e.target.closest ? e.target.closest('[data-admin-analyze],[data-admin-save],[data-admin-clear]') : null;
    if(!el) return;
    if(el.hasAttribute('data-admin-analyze')) analyze();
    else if(el.hasAttribute('data-admin-save')) save();
    else { _pending = null; var ta = $('#admin-paste'); if(ta) ta.value = ''; say(''); refreshPreview(); }
  });

  window.renderAdminPaste = renderPaste;
})();
